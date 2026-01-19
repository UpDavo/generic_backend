from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from datetime import datetime, timedelta, date
from django.db.models import Sum, Q, F, DecimalField, ExpressionWrapper
from io import BytesIO
from collections import defaultdict
from decimal import Decimal
import pandas as pd

from tada.models import SalesRecord, SalesRecordQueryLog
from tada.utils.constants import APPS


class TopSkusByRegionWeeklyReportView(APIView):
    """
    Vista para obtener el TOP 5 de SKUs por región y semana.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener TOP 5 SKUs por región y semana.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - retornable: "retornable" o "no retornable" (opcional, default: todos)
        - regions: Lista de regiones separadas por coma (opcional, default: todas)

        Returns:
        {
            "Region A": {
                "Producto 1": {
                    "total": 500.25,
                    "sku_vtex": "SKU123",
                    "w1": 100.5,
                    "w2": 150.75,
                    ...
                },
                ...
            },
            ...
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

        # Validar parámetro retornable (opcional)
        retornable = request.query_params.get('retornable', '').strip().lower()
        if retornable and retornable not in ['retornable', 'no retornable', 'noretornable', 'no_retornable']:
            return Response(
                {'error': 'retornable debe ser "retornable" o "no retornable" (opcional)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Normalizar valor
        if retornable in ['noretornable', 'no_retornable']:
            retornable = 'no retornable'
        
        # Validar parámetro report_type (opcional)
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
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

        # Obtener regiones (opcional)
        regions_param = request.query_params.get('regions', '').strip()
        regions_filter = [r.strip() for r in regions_param.split(
            ',') if r.strip()] if regions_param else None

        # Generar lista de semanas
        weeks_list = self._generate_weeks_list(
            start_year, end_year, start_week, end_week)

        if not weeks_list:
            return Response(
                {'error': 'No se pudieron generar semanas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Si no se especifica retornable, obtener ambos tipos por separado
        if not retornable:
            # Obtener datos de retornables
            sales_data_retornable = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                'retornable', regions_filter, report_type
            )
            
            # Obtener datos de no retornables
            sales_data_no_retornable = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                'no retornable', regions_filter, report_type
            )
            
            # Construir respuesta con ambos tipos
            response_data = {
                'retornable': self._build_response(sales_data_retornable, weeks_list),
                'no_retornable': self._build_response(sales_data_no_retornable, weeks_list)
            }
            
            records_count = (
                sum(len(products) for products in response_data['retornable'].values()) +
                sum(len(products) for products in response_data['no_retornable'].values())
            )
        else:
            # Obtener datos según el tipo especificado
            sales_data = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                retornable, regions_filter, report_type
            )
            
            # Construir respuesta estructurada
            response_data = self._build_response(sales_data, weeks_list)
            records_count = sum(len(products) for products in response_data.values())

        # Crear log de la consulta
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='TOP_SKUS_REGION',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'retornable': retornable if retornable else 'both',
                    'regions': regions_filter if regions_filter else 'all',
                    'report_type': report_type
                },
                records_returned=records_count
            )
        except Exception as e:
            # No fallar si hay error en el log
            print(f"Error creando log: {e}")

        return Response(response_data, status=status.HTTP_200_OK)

    def _generate_weeks_list(self, start_year, end_year, start_week, end_week):
        """
        Generar lista de identificadores de semanas (ej: "w1", "w2", ...).
        """
        weeks_list = []

        if start_year == end_year:
            for week_num in range(start_week, end_week + 1):
                weeks_list.append(f"w{week_num}")
        else:
            # Primer año: desde start_week hasta 53
            for week_num in range(start_week, 54):
                weeks_list.append(f"w{week_num}")

            # Años intermedios: todas las semanas
            for year in range(start_year + 1, end_year):
                for week_num in range(1, 54):
                    weeks_list.append(f"w{week_num}")

            # Último año: desde 1 hasta end_week
            for week_num in range(1, end_week + 1):
                weeks_list.append(f"w{week_num}")

        return weeks_list

    def _get_sales_data(self, start_year, end_year, start_week, end_week, retornable, regions_filter, report_type='hectolitros'):
        """
        Obtener datos de ventas agrupados por región, producto, año y semana.

        Returns:
            dict: {
                region: {
                    (product_name, sku_vtex): {
                        (year, week): total_value
                    }
                }
            }
        """
        # Construir filtro base
        filters = Q(
            deleted_at__isnull=True,
            year__isnull=False,
            week__isnull=False,
            poc_region__isnull=False
        )
        
        # Filtro específico según el tipo de reporte
        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:  # caja
            filters &= Q(orders__isnull=False, units_assigned__isnull=False, unidades_por_caja__isnull=False)

        # Filtrar por retornable (opcional)
        if retornable:
            if retornable == 'retornable':
                filters &= Q(retornable__iexact='retornable')
            elif retornable == 'no retornable':
                filters &= Q(retornable__iexact='no retornable')

        # Filtrar por regiones si se especificaron
        if regions_filter:
            filters &= Q(poc_region__in=regions_filter)

        # Filtrar por rango de semanas
        if start_year == end_year:
            filters &= Q(year=start_year, week__gte=start_week,
                         week__lte=end_week)
        else:
            # Construir filtro complejo para múltiples años
            year_filters = Q()

            # Primer año
            year_filters |= Q(year=start_year, week__gte=start_week)

            # Años intermedios
            if end_year - start_year > 1:
                year_filters |= Q(year__gt=start_year, year__lt=end_year)

            # Último año
            year_filters |= Q(year=end_year, week__lte=end_week)

            filters &= year_filters

        # Obtener datos agrupados con anotación según tipo de reporte
        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                'poc_region',
                'name_homologated',
                'name',
                'sku_vtex',
                'year',
                'week'
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by('poc_region', 'name_homologated', 'year', 'week')
        else:  # caja
            sales_queryset = SalesRecord.objects.filter(filters).values(
                'poc_region',
                'name_homologated',
                'name',
                'sku_vtex',
                'year',
                'week'
            ).annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
            ).order_by('poc_region', 'name_homologated', 'year', 'week')

        # Organizar datos en estructura anidada
        data_by_region = defaultdict(
            lambda: defaultdict(lambda: defaultdict(Decimal)))

        for item in sales_queryset:
            region = item['poc_region']
            product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
            sku = item['sku_vtex']
            year = item['year']
            week = item['week']
            value = Decimal(
                str(item['total_value'])) if item['total_value'] else Decimal('0')

            # Usar tupla (producto, sku) como clave
            product_key = (product_name, sku)
            data_by_region[region][product_key][(year, week)] = value

        return data_by_region

    def _build_response(self, sales_data, weeks_list):
        """
        Construir respuesta JSON con TOP 5 productos por región (basado en hectolitros).
        """
        response = {}

        for region, products_data in sales_data.items():
            # Calcular total por producto
            products_totals = {}
            for product_key, weeks_data in products_data.items():
                total = sum(weeks_data.values())
                products_totals[product_key] = total

            # Obtener TOP 5 productos por total de hectolitros
            top_5_products = sorted(
                products_totals.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            # Construir estructura para esta región
            region_data = {}
            for product_key, total in top_5_products:
                product_name, sku = product_key
                weeks_data = sales_data[region][product_key]

                product_info = {
                    'total': round(float(total), 2),
                    'sku_vtex': sku
                }

                # Agregar datos por semana
                for week_id in weeks_list:
                    # Extraer año y número de semana del ID
                    week_num = int(week_id[1:])  # Remover 'w'

                    # Buscar el valor en weeks_data
                    week_value = Decimal('0')
                    for (year, week), value in weeks_data.items():
                        if week == week_num:
                            week_value += value

                    product_info[week_id] = round(float(week_value), 2)

                region_data[product_name] = product_info

            if region_data:
                response[region] = region_data

        return response


class TopSkusByRegionWeeklyReportDownloadView(APIView):
    """
    Vista para descargar el TOP 5 de SKUs por región y semana en Excel.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar TOP 5 SKUs por región y semana en Excel.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - retornable: "retornable" o "no retornable" (opcional, default: todos)
        - regions: Lista de regiones separadas por coma (opcional, default: todas)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)

        Returns:
        Archivo Excel con el reporte estructurado por regiones y productos
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

        retornable = request.query_params.get('retornable', '').strip().lower()
        if retornable and retornable not in ['retornable', 'no retornable', 'noretornable', 'no_retornable']:
            return Response(
                {'error': 'retornable debe ser "retornable" o "no retornable" (opcional)'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Normalizar valor
        if retornable in ['noretornable', 'no_retornable']:
            retornable = 'no retornable'
        
        # Validar parámetro report_type (opcional)
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
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

        regions_param = request.query_params.get('regions', '').strip()
        regions_filter = [r.strip() for r in regions_param.split(
            ',') if r.strip()] if regions_param else None

        # Generar lista de semanas
        weeks_list = self._generate_weeks_list(
            start_year, end_year, start_week, end_week)

        if not weeks_list:
            return Response(
                {'error': 'No se pudieron generar semanas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Si no se especifica retornable, obtener ambos tipos por separado
        if not retornable:
            # Obtener datos de retornables
            sales_data_retornable = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                'retornable', regions_filter, report_type
            )
            
            # Obtener datos de no retornables
            sales_data_no_retornable = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                'no retornable', regions_filter, report_type
            )
            
            # Construir respuesta con ambos tipos
            response_data_retornable = self._build_response(sales_data_retornable, weeks_list)
            response_data_no_retornable = self._build_response(sales_data_no_retornable, weeks_list)
            
            # Crear DataFrames separados
            df_retornable = self._build_excel_dataframe(response_data_retornable, weeks_list)
            df_no_retornable = self._build_excel_dataframe(response_data_no_retornable, weeks_list)
            
            records_count = len(df_retornable) + len(df_no_retornable)
            
            retornable_label = 'ambos'
        else:
            # Obtener datos según el tipo especificado
            sales_data = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                retornable, regions_filter, report_type
            )
            
            # Construir respuesta estructurada
            response_data = self._build_response(sales_data, weeks_list)
            
            # Crear DataFrame para Excel
            df = self._build_excel_dataframe(response_data, weeks_list)
            
            records_count = len(df)
            retornable_label = 'retornables' if retornable == 'retornable' else 'no_retornables'

        # Crear log de la descarga
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='TOP_SKUS_REGION_DOWNLOAD',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'retornable': retornable if retornable else 'both',
                    'regions': regions_filter if regions_filter else 'all',
                    'report_type': report_type
                },
                records_returned=records_count
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        # Generar archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if not retornable:
                # Si es ambos, crear dos hojas
                df_retornable.to_excel(writer, sheet_name='Retornables', index=False)
                df_no_retornable.to_excel(writer, sheet_name='No Retornables', index=False)
                
                # Ajustar ancho de columnas para ambas hojas
                for sheet_name, df_sheet in [('Retornables', df_retornable), ('No Retornables', df_no_retornable)]:
                    worksheet = writer.sheets[sheet_name]
                    for idx, col in enumerate(df_sheet.columns, 1):
                        max_length = max(
                            df_sheet[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 50)
            else:
                # Si es específico, crear una sola hoja
                df.to_excel(writer, sheet_name='TOP 5 SKUs', index=False)
                
                # Ajustar ancho de columnas
                worksheet = writer.sheets['TOP 5 SKUs']
                for idx, col in enumerate(df.columns, 1):
                    max_length = max(
                        df[col].astype(str).apply(len).max(),
                        len(str(col))
                    )
                    worksheet.column_dimensions[chr(64 + idx)].width = min(max_length + 2, 50)

        output.seek(0)

        # Generar nombre de archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        type_label = 'hectolitros' if report_type == 'hectolitros' else 'cajas'
        filename = f'top5_skus_{type_label}_{retornable_label}_{start_year}W{start_week}_{end_year}W{end_week}_{timestamp}.xlsx'

        # Crear respuesta HTTP
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _generate_weeks_list(self, start_year, end_year, start_week, end_week):
        """Generar lista de identificadores de semanas."""
        weeks_list = []

        if start_year == end_year:
            for week_num in range(start_week, end_week + 1):
                weeks_list.append(f"w{week_num}")
        else:
            for week_num in range(start_week, 54):
                weeks_list.append(f"w{week_num}")

            for year in range(start_year + 1, end_year):
                for week_num in range(1, 54):
                    weeks_list.append(f"w{week_num}")

            for week_num in range(1, end_week + 1):
                weeks_list.append(f"w{week_num}")

        return weeks_list

    def _get_sales_data(self, start_year, end_year, start_week, end_week, retornable, regions_filter, report_type='hectolitros'):
        """Obtener datos de ventas (mismo método que la vista anterior)."""
        filters = Q(
            deleted_at__isnull=True,
            year__isnull=False,
            week__isnull=False,
            poc_region__isnull=False
        )
        
        # Filtro específico según el tipo de reporte
        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:  # caja
            filters &= Q(orders__isnull=False, units_assigned__isnull=False, unidades_por_caja__isnull=False)

        if retornable:
            if retornable == 'retornable':
                filters &= Q(retornable__iexact='retornable')
            elif retornable == 'no retornable':
                filters &= Q(retornable__iexact='no retornable')

        if regions_filter:
            filters &= Q(poc_region__in=regions_filter)

        if start_year == end_year:
            filters &= Q(year=start_year, week__gte=start_week,
                         week__lte=end_week)
        else:
            year_filters = Q()
            year_filters |= Q(year=start_year, week__gte=start_week)
            if end_year - start_year > 1:
                year_filters |= Q(year__gt=start_year, year__lt=end_year)
            year_filters |= Q(year=end_year, week__lte=end_week)
            filters &= year_filters

        # Obtener datos agrupados con anotación según tipo de reporte
        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                'poc_region',
                'name_homologated',
                'name',
                'sku_vtex',
                'year',
                'week'
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by('poc_region', 'name_homologated', 'year', 'week')
        else:  # caja
            sales_queryset = SalesRecord.objects.filter(filters).values(
                'poc_region',
                'name_homologated',
                'name',
                'sku_vtex',
                'year',
                'week'
            ).annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
            ).order_by('poc_region', 'name_homologated', 'year', 'week')

        data_by_region = defaultdict(
            lambda: defaultdict(lambda: defaultdict(Decimal)))

        for item in sales_queryset:
            region = item['poc_region']
            product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
            sku = item['sku_vtex']
            year = item['year']
            week = item['week']
            value = Decimal(
                str(item['total_value'])) if item['total_value'] else Decimal('0')

            product_key = (product_name, sku)
            data_by_region[region][product_key][(year, week)] = value

        return data_by_region

    def _build_response(self, sales_data, weeks_list):
        """Construir respuesta JSON (mismo método que la vista anterior)."""
        response = {}

        for region, products_data in sales_data.items():
            products_totals = {}
            for product_key, weeks_data in products_data.items():
                total = sum(weeks_data.values())
                products_totals[product_key] = total

            top_5_products = sorted(
                products_totals.items(),
                key=lambda x: x[1],
                reverse=True
            )[:5]

            region_data = {}
            for product_key, total in top_5_products:
                product_name, sku = product_key
                weeks_data = sales_data[region][product_key]

                product_info = {
                    'total': round(float(total), 2),
                    'sku_vtex': sku
                }

                for week_id in weeks_list:
                    week_num = int(week_id[1:])

                    week_value = Decimal('0')
                    for (year, week), value in weeks_data.items():
                        if week == week_num:
                            week_value += value

                    product_info[week_id] = round(float(week_value), 2)

                region_data[product_name] = product_info

            if region_data:
                response[region] = region_data

        return response

    def _build_excel_dataframe(self, response_data, weeks_list):
        """
        Construir DataFrame para exportar a Excel.
        """
        rows = []

        for region, products in response_data.items():
            for product_name, product_data in products.items():
                row = {
                    'Region': region,
                    'Producto': product_name,
                    'SKU': product_data.get('sku_vtex', ''),
                    'Total': product_data.get('total', 0)
                }

                # Agregar columnas de semanas
                for week_id in weeks_list:
                    row[week_id.upper()] = product_data.get(week_id, 0)

                rows.append(row)

        df = pd.DataFrame(rows)

        # Ordenar por región y total descendente
        if not df.empty:
            df = df.sort_values(['Region', 'Total'], ascending=[True, False])

        return df
