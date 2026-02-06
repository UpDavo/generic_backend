from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from datetime import datetime
from django.db.models import Sum, Q
from io import BytesIO
from decimal import Decimal
import pandas as pd

from tada.models import SalesRecord, SalesRecordQueryLog, YearlySalesData
from tada.utils.constants import APPS


class HectolitresYearlyComparisonReportView(APIView):
    """
    Vista para obtener comparativa de hectolitros por año para las mismas semanas.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener comparativa de hectolitros por año.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - report_type: "hectolitros" o "caja" (opcional, default: "hectolitros")

        Returns:
        {
            "totals": {
                "2024": 1500.50,
                "2025": 1800.75,
                "2026": 2100.25
            },
            "cities": {
                "Lima": {
                    "2024": 800.25,
                    "2025": 950.50,
                    "2026": 1100.75
                },
                "Arequipa": {
                    "2024": 700.25,
                    "2025": 850.25,
                    "2026": 999.50
                }
            }
        }
        """
        # Validar parámetros requeridos
        try:
            start_year = int(request.query_params.get('start_year'))
            end_year = int(request.query_params.get('end_year'))
            start_week = int(request.query_params.get('start_week'))
            end_week = int(request.query_params.get('end_week'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'start_year, end_year, start_week y end_week son requeridos y deben ser enteros'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar parámetro report_type
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar rangos
        if start_week < 1 or start_week > 53 or end_week < 1 or end_week > 53:
            return Response(
                {'error': 'start_week y end_week deben estar entre 1 y 53'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'start_year no puede ser mayor que end_year'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener datos de ventas por año
        response_data = self._get_data_by_year(
            start_year, end_year, start_week, end_week, report_type
        )

        # Crear log de la consulta
        try:
            total_years = end_year - start_year + 1
            
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='YEARLY_COMPARISON',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'report_type': f'yearly_comparison_{report_type}'
                },
                records_returned=total_years
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_data_by_year(self, start_year, end_year, start_week, end_week, report_type):
        """
        Obtener suma por año para las mismas semanas según el tipo de reporte.

        Returns:
            dict: {
                "totals": {"2024": 1500.50, ...},
                "cities": {"Lima": {"2024": 800.25, ...}, ...}
            }
        """
        from django.db.models import F, ExpressionWrapper, DecimalField
        from datetime import datetime, timedelta
        
        totals = {}
        cities_data = {}

        for year in range(start_year, end_year + 1):
            # Calcular fechas aproximadas para el rango de semanas
            # Usamos ISO 8601 para las semanas
            start_date = datetime.strptime(f'{year}-W{start_week:02d}-1', "%Y-W%W-%w").date()
            # Para la fecha final, tomamos el último día de la semana final
            end_date = datetime.strptime(f'{year}-W{end_week:02d}-0', "%Y-W%W-%w").date()
            
            # Primero, verificar si hay datos en YearlySalesData para este período
            yearly_total_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=True  # Total general
            ).aggregate(total=Sum('total'))
            
            yearly_cities_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=False  # Datos por ciudad
            ).values('city').annotate(total=Sum('total'))
            
            # Si hay datos en YearlySalesData, usarlos
            if yearly_total_data['total'] is not None or yearly_cities_data.exists():
                # Usar datos de YearlySalesData
                total = yearly_total_data['total'] or Decimal('0')
                totals[str(year)] = round(float(total), 2)
                
                for city_data in yearly_cities_data:
                    city_name = city_data['city']
                    city_total = city_data['total'] or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)
                    
            else:
                # Calcular desde SalesRecord (lógica existente)
                if report_type == 'hectolitros':
                    # Suma total de hectolitros
                    result = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        hectolitros__isnull=False
                    ).aggregate(
                        total=Sum('hectolitros')
                    )
                    total = result['total'] or Decimal('0')
                    
                    # Suma por ciudad
                    city_results = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        hectolitros__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        total=Sum('hectolitros')
                    ).order_by('poc_city')
                    
                else:  # caja
                    # Calcular cajas: (orders * units_assigned) / unidades_por_caja
                    records = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        unidades_por_caja__isnull=False,
                        unidades_por_caja__gt=0,
                        orders__isnull=False,
                        units_assigned__isnull=False
                    ).annotate(
                        cajas=ExpressionWrapper(
                            (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                            output_field=DecimalField()
                        )
                    ).aggregate(
                        total=Sum('cajas')
                    )
                    total = records['total'] or Decimal('0')
                    
                    # Suma por ciudad
                    city_results = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        unidades_por_caja__isnull=False,
                        unidades_por_caja__gt=0,
                        orders__isnull=False,
                        units_assigned__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        cajas=Sum(
                            ExpressionWrapper(
                                (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                                output_field=DecimalField()
                            )
                        )
                    ).order_by('poc_city')

                # Guardar total del año (calculado)
                totals[str(year)] = round(float(total), 2)

                # Procesar resultados por ciudad
                for city_item in city_results:
                    city_name = city_item['poc_city']
                    city_total = city_item.get('total') or city_item.get('cajas') or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)

        return {
            'totals': totals,
            'cities': cities_data
        }


class HectolitresYearlyComparisonReportDownloadView(APIView):
    """
    Vista para descargar comparativa de hectolitros por año en Excel.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar comparativa de hectolitros por año en Excel.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - report_type: "hectolitros" o "caja" (opcional, default: "hectolitros")

        Returns:
        Archivo Excel con comparativa de hectolitros por año
        """
        # Validar parámetros (mismo código que la vista anterior)
        try:
            start_year = int(request.query_params.get('start_year'))
            end_year = int(request.query_params.get('end_year'))
            start_week = int(request.query_params.get('start_week'))
            end_week = int(request.query_params.get('end_week'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'start_year, end_year, start_week y end_week son requeridos y deben ser enteros'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar parámetro report_type
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_week < 1 or start_week > 53 or end_week < 1 or end_week > 53:
            return Response(
                {'error': 'start_week y end_week deben estar entre 1 y 53'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'start_year no puede ser mayor que end_year'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener datos de ventas por año
        data = self._get_data_by_year(
            start_year, end_year, start_week, end_week, report_type
        )

        # Crear DataFrame para totales
        column_name = 'Hectolitros' if report_type == 'hectolitros' else 'Cajas'
        df_totals = pd.DataFrame([
            {'Año': year, column_name: value}
            for year, value in data['totals'].items()
        ])
        
        # Crear DataFrame para ciudades
        cities_rows = []
        for city, years_data in data['cities'].items():
            row = {'Ciudad': city}
            for year in range(start_year, end_year + 1):
                year_str = str(year)
                if year_str in years_data:
                    row[year_str] = years_data[year_str]
                else:
                    row[year_str] = 0.0
            cities_rows.append(row)
        
        df_cities = pd.DataFrame(cities_rows) if cities_rows else pd.DataFrame()

        # Crear log de la descarga
        try:
            total_years = end_year - start_year + 1
            
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='YEARLY_COMPARISON_DOWNLOAD',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'report_type': f'yearly_comparison_{report_type}'
                },
                records_returned=total_years
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        # Generar archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Hoja de totales
            df_totals.to_excel(writer, sheet_name='Totales', index=False)
            
            # Hoja de ciudades
            if not df_cities.empty:
                df_cities.to_excel(writer, sheet_name='Por Ciudad', index=False)
            
            # Ajustar ancho de columnas - Totales
            worksheet_totals = writer.sheets['Totales']
            for idx, col in enumerate(df_totals.columns, 1):
                max_length = max(
                    df_totals[col].astype(str).apply(len).max(),
                    len(str(col))
                )
                worksheet_totals.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 20)
            
            # Ajustar ancho de columnas - Ciudades
            if not df_cities.empty:
                worksheet_cities = writer.sheets['Por Ciudad']
                for idx, col in enumerate(df_cities.columns, 1):
                    max_length = max(
                        df_cities[col].astype(str).apply(len).max(),
                        len(str(col))
                    )
                    worksheet_cities.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 20)

        output.seek(0)

        # Generar nombre de archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        type_label = 'hectolitros' if report_type == 'hectolitros' else 'cajas'
        filename = f'comparativa_{type_label}_{start_year}_{end_year}_W{start_week}-W{end_week}_{timestamp}.xlsx'

        # Crear respuesta HTTP
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _get_data_by_year(self, start_year, end_year, start_week, end_week, report_type):
        """
        Obtener suma por año para las mismas semanas según el tipo de reporte.
        (Mismo método que la vista anterior)
        """
        from django.db.models import F, ExpressionWrapper, DecimalField
        from datetime import datetime, timedelta
        
        totals = {}
        cities_data = {}

        for year in range(start_year, end_year + 1):
            # Calcular fechas aproximadas para el rango de semanas
            # Usamos ISO 8601 para las semanas
            start_date = datetime.strptime(f'{year}-W{start_week:02d}-1', "%Y-W%W-%w").date()
            # Para la fecha final, tomamos el último día de la semana final
            end_date = datetime.strptime(f'{year}-W{end_week:02d}-0', "%Y-W%W-%w").date()
            
            # Primero, verificar si hay datos en YearlySalesData para este período
            yearly_total_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=True  # Total general
            ).aggregate(total=Sum('total'))
            
            yearly_cities_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=False  # Datos por ciudad
            ).values('city').annotate(total=Sum('total'))
            
            # Si hay datos en YearlySalesData, usarlos
            if yearly_total_data['total'] is not None or yearly_cities_data.exists():
                # Usar datos de YearlySalesData
                total = yearly_total_data['total'] or Decimal('0')
                totals[str(year)] = round(float(total), 2)
                
                for city_data in yearly_cities_data:
                    city_name = city_data['city']
                    city_total = city_data['total'] or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)
                    
            else:
                # Calcular desde SalesRecord (lógica existente)
                if report_type == 'hectolitros':
                    # Suma total de hectolitros
                    result = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        hectolitros__isnull=False
                    ).aggregate(
                        total=Sum('hectolitros')
                    )
                    total = result['total'] or Decimal('0')
                    
                    # Suma por ciudad
                    city_results = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        hectolitros__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        total=Sum('hectolitros')
                    ).order_by('poc_city')
                    
                else:  # caja
                    # Calcular cajas: (orders * units_assigned) / unidades_por_caja
                    records = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        unidades_por_caja__isnull=False,
                        unidades_por_caja__gt=0,
                        orders__isnull=False,
                        units_assigned__isnull=False
                    ).annotate(
                        cajas=ExpressionWrapper(
                            (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                            output_field=DecimalField()
                        )
                    ).aggregate(
                        total=Sum('cajas')
                    )
                    total = records['total'] or Decimal('0')
                    
                    # Suma por ciudad
                    city_results = SalesRecord.objects.filter(
                        deleted_at__isnull=True,
                        year=year,
                        week__gte=start_week,
                        week__lte=end_week,
                        unidades_por_caja__isnull=False,
                        unidades_por_caja__gt=0,
                        orders__isnull=False,
                        units_assigned__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        cajas=Sum(
                            ExpressionWrapper(
                                (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                                output_field=DecimalField()
                            )
                        )
                    ).order_by('poc_city')

                # Guardar total del año (calculado)
                totals[str(year)] = round(float(total), 2)

                # Procesar resultados por ciudad
                for city_item in city_results:
                    city_name = city_item['poc_city']
                    city_total = city_item.get('total') or city_item.get('cajas') or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)

        return {
            'totals': totals,
            'cities': cities_data
        }
