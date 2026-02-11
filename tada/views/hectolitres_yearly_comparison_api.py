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
    Vista para obtener comparativa de hectolitros por año para los mismos días de un mes.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener comparativa de hectolitros por año.

        Query params:
        - start_month: Mes-año inicial en formato YYYY-MM (requerido, ej: "2025-01")
        - end_month: Mes-año final en formato YYYY-MM (requerido, ej: "2026-01")
        - start_day: Día inicial del rango (requerido, 1-31)
        - end_day: Día final del rango (requerido, 1-31)
        - report_type: "hectolitros" o "caja" (opcional, default: "hectolitros")

        Returns:
        {
            "totals": {
                "2025": 3700.55,
                "2026": 3479.68
            },
            "cities": {
                "QUITO": {
                    "2025": 1845.70,
                    "2026": 2265.71
                },
                "GUAYAQUIL": {
                    "2025": 1305.50,
                    "2026": 688.20
                }
            }
        }
        """
        # Validar parámetros requeridos
        start_month_str = request.query_params.get('start_month')
        end_month_str = request.query_params.get('end_month')

        if not start_month_str or not end_month_str:
            return Response(
                {'error': 'start_month y end_month son requeridos (formato YYYY-MM)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_year, start_month_num = map(int, start_month_str.split('-'))
            end_year, end_month_num = map(int, end_month_str.split('-'))
        except (ValueError, AttributeError):
            return Response(
                {'error': 'start_month y end_month deben tener formato YYYY-MM (ej: 2025-01)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_day = int(request.query_params.get('start_day'))
            end_day = int(request.query_params.get('end_day'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'start_day y end_day son requeridos y deben ser enteros'},
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
        if start_month_num < 1 or start_month_num > 12 or end_month_num < 1 or end_month_num > 12:
            return Response(
                {'error': 'El mes debe estar entre 01 y 12'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_day < 1 or start_day > 31 or end_day < 1 or end_day > 31:
            return Response(
                {'error': 'start_day y end_day deben estar entre 1 y 31'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'El año de start_month no puede ser mayor que el de end_month'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener datos de ventas por año
        response_data = self._get_data_by_year(
            start_year, end_year, start_month_num, end_month_num, start_day, end_day, report_type
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
                    'start_month': start_month_num,
                    'end_month': end_month_num,
                    'start_day': start_day,
                    'end_day': end_day,
                    'report_type': f'yearly_comparison_{report_type}'
                },
                records_returned=total_years
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        return Response(response_data, status=status.HTTP_200_OK)

    def _get_data_by_year(self, start_year, end_year, start_month_num, end_month_num, start_day, end_day, report_type):
        """
        Obtener suma por año para los mismos días de un mes según el tipo de reporte.

        Returns:
            dict: {
                "totals": {"2025": 3700.55, ...},
                "cities": {"QUITO": {"2025": 1845.70, ...}, ...}
            }
        """
        from django.db.models import F, ExpressionWrapper, DecimalField
        import calendar
        
        totals = {}
        cities_data = {}

        for year in range(start_year, end_year + 1):
            # Determinar el mes a usar para este año
            # Si es el año de inicio usa start_month_num, si es el de fin usa end_month_num
            # Si todos los años tienen el mismo mes (caso típico), ambos son iguales
            month_num = start_month_num if year == start_year else end_month_num
            if start_month_num == end_month_num:
                month_num = start_month_num

            # Construir fechas exactas para el rango
            # Ajustar end_day al máximo del mes si excede
            max_day = calendar.monthrange(year, month_num)[1]
            actual_start_day = min(start_day, max_day)
            actual_end_day = min(end_day, max_day)

            from datetime import date as date_cls
            start_date = date_cls(year, month_num, actual_start_day)
            end_date = date_cls(year, month_num, actual_end_day)

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
                total = yearly_total_data['total'] or Decimal('0')
                totals[str(year)] = round(float(total), 2)
                
                for city_data in yearly_cities_data:
                    city_name = city_data['city']
                    city_total = city_data['total'] or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)
                    
            else:
                # Calcular desde SalesRecord filtrando por año, mes y rango de días
                base_filter = {
                    'deleted_at__isnull': True,
                    'year': year,
                    'month': month_num,
                    'day__gte': actual_start_day,
                    'day__lte': actual_end_day,
                }

                if report_type == 'hectolitros':
                    result = SalesRecord.objects.filter(
                        **base_filter,
                        hectolitros__isnull=False
                    ).aggregate(
                        total=Sum('hectolitros')
                    )
                    total = result['total'] or Decimal('0')
                    
                    city_results = SalesRecord.objects.filter(
                        **base_filter,
                        hectolitros__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        total=Sum('hectolitros')
                    ).order_by('poc_city')
                    
                else:  # caja
                    records = SalesRecord.objects.filter(
                        **base_filter,
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
                    
                    city_results = SalesRecord.objects.filter(
                        **base_filter,
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

                totals[str(year)] = round(float(total), 2)

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
        - start_month: Mes-año inicial en formato YYYY-MM (requerido)
        - end_month: Mes-año final en formato YYYY-MM (requerido)
        - start_day: Día inicial del rango (requerido, 1-31)
        - end_day: Día final del rango (requerido, 1-31)
        - report_type: "hectolitros" o "caja" (opcional, default: "hectolitros")

        Returns:
        Archivo Excel con comparativa de hectolitros por año
        """
        # Validar parámetros requeridos
        start_month_str = request.query_params.get('start_month')
        end_month_str = request.query_params.get('end_month')

        if not start_month_str or not end_month_str:
            return Response(
                {'error': 'start_month y end_month son requeridos (formato YYYY-MM)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_year, start_month_num = map(int, start_month_str.split('-'))
            end_year, end_month_num = map(int, end_month_str.split('-'))
        except (ValueError, AttributeError):
            return Response(
                {'error': 'start_month y end_month deben tener formato YYYY-MM (ej: 2025-01)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_day = int(request.query_params.get('start_day'))
            end_day = int(request.query_params.get('end_day'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'start_day y end_day son requeridos y deben ser enteros'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar parámetro report_type
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_month_num < 1 or start_month_num > 12 or end_month_num < 1 or end_month_num > 12:
            return Response(
                {'error': 'El mes debe estar entre 01 y 12'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_day < 1 or start_day > 31 or end_day < 1 or end_day > 31:
            return Response(
                {'error': 'start_day y end_day deben estar entre 1 y 31'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'El año de start_month no puede ser mayor que el de end_month'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener datos de ventas por año
        data = self._get_data_by_year(
            start_year, end_year, start_month_num, end_month_num, start_day, end_day, report_type
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
                    'start_month': start_month_num,
                    'end_month': end_month_num,
                    'start_day': start_day,
                    'end_day': end_day,
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
        filename = f'comparativa_{type_label}_{start_year}_{end_year}_M{start_month_num}_D{start_day}-D{end_day}_{timestamp}.xlsx'

        # Crear respuesta HTTP
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _get_data_by_year(self, start_year, end_year, start_month_num, end_month_num, start_day, end_day, report_type):
        """
        Obtener suma por año para los mismos días de un mes según el tipo de reporte.
        (Mismo método que la vista anterior)
        """
        from django.db.models import F, ExpressionWrapper, DecimalField
        import calendar
        
        totals = {}
        cities_data = {}

        for year in range(start_year, end_year + 1):
            month_num = start_month_num if year == start_year else end_month_num
            if start_month_num == end_month_num:
                month_num = start_month_num

            max_day = calendar.monthrange(year, month_num)[1]
            actual_start_day = min(start_day, max_day)
            actual_end_day = min(end_day, max_day)

            from datetime import date as date_cls
            start_date = date_cls(year, month_num, actual_start_day)
            end_date = date_cls(year, month_num, actual_end_day)

            # Primero, verificar si hay datos en YearlySalesData para este período
            yearly_total_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=True
            ).aggregate(total=Sum('total'))
            
            yearly_cities_data = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                report_type=report_type,
                city__isnull=False
            ).values('city').annotate(total=Sum('total'))
            
            if yearly_total_data['total'] is not None or yearly_cities_data.exists():
                total = yearly_total_data['total'] or Decimal('0')
                totals[str(year)] = round(float(total), 2)
                
                for city_data in yearly_cities_data:
                    city_name = city_data['city']
                    city_total = city_data['total'] or Decimal('0')
                    
                    if city_name not in cities_data:
                        cities_data[city_name] = {}
                    
                    cities_data[city_name][str(year)] = round(float(city_total), 2)
                    
            else:
                base_filter = {
                    'deleted_at__isnull': True,
                    'year': year,
                    'month': month_num,
                    'day__gte': actual_start_day,
                    'day__lte': actual_end_day,
                }

                if report_type == 'hectolitros':
                    result = SalesRecord.objects.filter(
                        **base_filter,
                        hectolitros__isnull=False
                    ).aggregate(
                        total=Sum('hectolitros')
                    )
                    total = result['total'] or Decimal('0')
                    
                    city_results = SalesRecord.objects.filter(
                        **base_filter,
                        hectolitros__isnull=False,
                        poc_city__isnull=False
                    ).values('poc_city').annotate(
                        total=Sum('hectolitros')
                    ).order_by('poc_city')
                    
                else:  # caja
                    records = SalesRecord.objects.filter(
                        **base_filter,
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
                    
                    city_results = SalesRecord.objects.filter(
                        **base_filter,
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

                totals[str(year)] = round(float(total), 2)

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
