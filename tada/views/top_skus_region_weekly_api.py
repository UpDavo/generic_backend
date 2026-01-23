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
        Obtener TOP 5 SKUs por región y semana con filtros jerárquicos opcionales.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - retornable: "retornable" o "no retornable" (opcional, default: todos)
        - regions: Lista de regiones separadas por coma (opcional, default: todas)
        - group_by_region: "true" o "false" (opcional, default: true) - Agrupar por región
        - group_by_city: "true" o "false" (opcional, default: false) - Agrupar por ciudad (requiere group_by_region)
        - group_by_poc: "true" o "false" (opcional, default: false) - Agrupar por POC (requiere group_by_city)

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
        O con jerarquía:
        {
            "Region A": {
                "Ciudad 1": {
                    "POC 1": {
                        "Producto 1": {...}
                    }
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

        # Obtener parámetros de agrupación jerárquica
        group_by_region = request.query_params.get('group_by_region', 'true').strip().lower() == 'true'
        group_by_city = request.query_params.get('group_by_city', 'false').strip().lower() == 'true'
        group_by_poc = request.query_params.get('group_by_poc', 'false').strip().lower() == 'true'

        # Validar jerarquía: city requiere region, poc requiere city
        if group_by_city and not group_by_region:
            return Response(
                {'error': 'group_by_city requiere que group_by_region sea true'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if group_by_poc and not group_by_city:
            return Response(
                {'error': 'group_by_poc requiere que group_by_city sea true'},
                status=status.HTTP_400_BAD_REQUEST
            )

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
                'retornable', regions_filter, report_type,
                group_by_region, group_by_city, group_by_poc
            )
            
            # Obtener datos de no retornables
            sales_data_no_retornable = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                'no retornable', regions_filter, report_type,
                group_by_region, group_by_city, group_by_poc
            )
            
            # Construir respuesta con ambos tipos
            response_data = {
                'retornable': self._build_response(sales_data_retornable, weeks_list, group_by_region, group_by_city, group_by_poc),
                'no_retornable': self._build_response(sales_data_no_retornable, weeks_list, group_by_region, group_by_city, group_by_poc)
            }
            
            records_count = (
                self._count_records(response_data['retornable'], group_by_region, group_by_city, group_by_poc) +
                self._count_records(response_data['no_retornable'], group_by_region, group_by_city, group_by_poc)
            )
        else:
            # Obtener datos según el tipo especificado
            sales_data = self._get_sales_data(
                start_year, end_year, start_week, end_week,
                retornable, regions_filter, report_type,
                group_by_region, group_by_city, group_by_poc
            )
            
            # Construir respuesta estructurada
            response_data = self._build_response(sales_data, weeks_list, group_by_region, group_by_city, group_by_poc)
            records_count = self._count_records(response_data, group_by_region, group_by_city, group_by_poc)

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
                    'report_type': report_type,
                    'group_by_region': group_by_region,
                    'group_by_city': group_by_city,
                    'group_by_poc': group_by_poc
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

    def _get_sales_data(self, start_year, end_year, start_week, end_week, retornable, regions_filter, report_type='hectolitros', group_by_region=True, group_by_city=False, group_by_poc=False):
        """
        Obtener datos de ventas agrupados con jerarquía flexible.

        Returns:
            dict: Estructura jerárquica según los parámetros de agrupación:
            - Solo región: {region: {(product_name, sku): {(year, week): value}}}
            - Región + ciudad: {region: {city: {(product_name, sku): {(year, week): value}}}}
            - Región + ciudad + POC: {region: {city: {poc: {(product_name, sku): {(year, week): value}}}}}
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

        # Determinar los campos para agrupar según la jerarquía
        grouping_fields = []
        if group_by_region:
            grouping_fields.append('poc_region')
        if group_by_city:
            grouping_fields.append('poc_city')
        if group_by_poc:
            grouping_fields.append('poc_id')
            grouping_fields.append('poc_name')
        
        # Siempre incluir producto, SKU, año y semana
        grouping_fields.extend(['name_homologated', 'name', 'sku_vtex', 'year', 'week'])

        # Obtener datos agrupados con anotación según tipo de reporte
        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by(*grouping_fields)
        else:  # caja
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
            ).order_by(*grouping_fields)

        # Organizar datos en estructura anidada según la jerarquía
        if not group_by_region:
            # Sin agrupación: solo productos
            data_structure = defaultdict(lambda: defaultdict(Decimal))
            for item in sales_queryset:
                product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
                sku = item['sku_vtex']
                year = item['year']
                week = item['week']
                value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')
                product_key = (product_name, sku)
                data_structure[product_key][(year, week)] = value
        elif group_by_region and not group_by_city:
            # Solo región
            data_structure = defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
            for item in sales_queryset:
                region = item['poc_region'] or 'Sin región'
                product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
                sku = item['sku_vtex']
                year = item['year']
                week = item['week']
                value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')
                product_key = (product_name, sku)
                data_structure[region][product_key][(year, week)] = value
        elif group_by_city and not group_by_poc:
            # Región + Ciudad
            data_structure = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal))))
            for item in sales_queryset:
                region = item['poc_region'] or 'Sin región'
                city = item['poc_city'] or 'Sin ciudad'
                product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
                sku = item['sku_vtex']
                year = item['year']
                week = item['week']
                value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')
                product_key = (product_name, sku)
                data_structure[region][city][product_key][(year, week)] = value
        else:
            # Región + Ciudad + POC
            data_structure = defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(
                        lambda: defaultdict(
                            lambda: defaultdict(Decimal)
                        )
                    )
                )
            )
            for item in sales_queryset:
                region = item['poc_region'] or 'Sin región'
                city = item['poc_city'] or 'Sin ciudad'
                poc_id = item['poc_id'] or 'Sin ID'
                poc_name = item['poc_name'] or 'Sin nombre'
                poc_key = f"{poc_id} - {poc_name}"
                product_name = item['name_homologated'] or item['name'] or 'Sin nombre'
                sku = item['sku_vtex']
                year = item['year']
                week = item['week']
                value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')
                product_key = (product_name, sku)
                data_structure[region][city][poc_key][product_key][(year, week)] = value

        return data_structure

    def _build_response(self, sales_data, weeks_list, group_by_region=True, group_by_city=False, group_by_poc=False):
        """
        Construir respuesta JSON con TOP 5 productos con jerarquía flexible.
        """
        if not group_by_region:
            # Sin agrupación por región: solo TOP 5 general
            return self._build_top5_for_level(sales_data, weeks_list)
        elif group_by_region and not group_by_city:
            # Solo región
            response = {}
            for region, products_data in sales_data.items():
                region_data = self._build_top5_for_level(products_data, weeks_list)
                if region_data:
                    response[region] = region_data
            return response
        elif group_by_city and not group_by_poc:
            # Región + Ciudad
            response = {}
            for region, cities_data in sales_data.items():
                region_response = {}
                for city, products_data in cities_data.items():
                    city_data = self._build_top5_for_level(products_data, weeks_list)
                    if city_data:
                        region_response[city] = city_data
                if region_response:
                    response[region] = region_response
            return response
        else:
            # Región + Ciudad + POC
            response = {}
            for region, cities_data in sales_data.items():
                region_response = {}
                for city, pocs_data in cities_data.items():
                    city_response = {}
                    for poc, products_data in pocs_data.items():
                        poc_data = self._build_top5_for_level(products_data, weeks_list)
                        if poc_data:
                            city_response[poc] = poc_data
                    if city_response:
                        region_response[city] = city_response
                if region_response:
                    response[region] = region_response
            return response

    def _build_top5_for_level(self, products_data, weeks_list):
        """
        Construir TOP 5 productos para un nivel específico de la jerarquía.
        """
        # Calcular total por producto
        products_totals = {}
        for product_key, weeks_data in products_data.items():
            total = sum(weeks_data.values())
            products_totals[product_key] = total

        # Obtener TOP 5 productos por total
        top_5_products = sorted(
            products_totals.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        # Construir estructura de productos
        level_data = {}
        for product_key, total in top_5_products:
            product_name, sku = product_key
            weeks_data = products_data[product_key]

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

            level_data[product_name] = product_info

        return level_data

    def _count_records(self, data, group_by_region=True, group_by_city=False, group_by_poc=False):
        """
        Contar recursivamente el número de productos en la estructura jerárquica.
        """
        if not isinstance(data, dict):
            return 0
        
        if not group_by_region:
            # Sin agrupación: contar productos directamente
            return len(data)
        elif group_by_region and not group_by_city:
            # Solo región: contar productos por región
            return sum(len(products) for products in data.values() if isinstance(products, dict))
        elif group_by_city and not group_by_poc:
            # Región + Ciudad
            count = 0
            for region_data in data.values():
                if isinstance(region_data, dict):
                    for city_data in region_data.values():
                        if isinstance(city_data, dict):
                            count += len(city_data)
            return count
        else:
            # Región + Ciudad + POC
            count = 0
            for region_data in data.values():
                if isinstance(region_data, dict):
                    for city_data in region_data.values():
                        if isinstance(city_data, dict):
                            for poc_data in city_data.values():
                                if isinstance(poc_data, dict):
                                    count += len(poc_data)
            return count


class TopSkusByRegionWeeklyReportDownloadView(APIView):
    """
    Vista para descargar el TOP 5 de SKUs por región y semana en Excel.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar TOP 5 SKUs por región y semana en Excel con filtros jerárquicos.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)
        - retornable: "retornable" o "no retornable" (opcional, default: todos)
        - regions: Lista de regiones separadas por coma (opcional, default: todas)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)
        - group_by_region: "true" o "false" (opcional, default: true)
        - group_by_city: "true" o "false" (opcional, default: false)
        - group_by_poc: "true" o "false" (opcional, default: false)

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
