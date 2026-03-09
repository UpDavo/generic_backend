from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from django.db.models import Sum, Q, F, DecimalField, ExpressionWrapper
from django.db.models.functions import Upper
from io import BytesIO
from collections import defaultdict
from decimal import Decimal
import pandas as pd

from tada.models import SalesRecord, SalesRecordQueryLog, VentasProductosCompra
from tada.utils.constants import APPS


def _group_skus_by_homologated(sku_codes):
    """
    Agrupar SKU codes por nombre homologado compartido desde VentasProductosCompra.
    Returns:
        tuple: (sku_to_group, groups_info)
        - sku_to_group: dict mapping sku_code -> group_key
        - groups_info: dict mapping group_key -> {sku_codes, product_name, homologated}
    """
    products = VentasProductosCompra.objects.filter(code__in=sku_codes)

    code_to_product = {}
    h_name_to_codes = {}

    for product in products:
        code_to_product[product.code] = product
        names = product.homologated_names or []
        for h_name in names:
            h_key = h_name.strip().lower()
            if h_key not in h_name_to_codes:
                h_name_to_codes[h_key] = {
                    'codes': set(),
                    'display_name': h_name.strip().upper()
                }
            h_name_to_codes[h_key]['codes'].add(product.code)

    sku_to_group = {}
    groups_info = {}
    used_codes = set()

    # Priorizar grupos más grandes
    for h_key, info in sorted(h_name_to_codes.items(), key=lambda x: -len(x[1]['codes'])):
        relevant_codes = sorted(
            [c for c in info['codes'] if c in sku_codes and c not in used_codes])
        if relevant_codes:
            group_key = info['display_name']
            for code in relevant_codes:
                sku_to_group[code] = group_key
                used_codes.add(code)
            if group_key not in groups_info:
                groups_info[group_key] = {
                    'sku_codes': relevant_codes,
                    'product_name': info['display_name'],
                    'homologated': True
                }
            else:
                groups_info[group_key]['sku_codes'] = sorted(
                    set(groups_info[group_key]['sku_codes'] + relevant_codes)
                )

    # SKUs sin nombre homologado o no encontrados en VentasProductosCompra
    for code in sku_codes:
        if code not in used_codes:
            product = code_to_product.get(code)
            name = product.name.upper() if product and product.name else code
            sku_to_group[code] = code
            groups_info[code] = {
                'sku_codes': [code],
                'product_name': name,
                'homologated': False
            }

    return sku_to_group, groups_info


class SKUDetailByCityPOCWeeklyReportView(APIView):
    """
    Vista para obtener detalle de un SKU específico agrupado por ciudad y POC.
    Filtra por rango de fechas y agrupa por semanas.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener detalle de ventas de uno o más SKUs por ciudad, POC y semana.

        Query params:
        - sku_code: Código(s) del SKU a consultar (requerido). Puede ser uno o varios separados por comas
        - start_date: Fecha inicial en formato YYYY-MM-DD (requerido)
        - end_date: Fecha final en formato YYYY-MM-DD (requerido)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)

        Ejemplo: sku_code=123456&start_date=2026-01-01&end_date=2026-01-31
        Ejemplo múltiple: sku_code=123456,789012,345678&start_date=2026-01-01&end_date=2026-01-31

        Returns:
        {
            "skus": {
                "123456": {
                    "product_name": "Nombre del Producto",
                    "cities": {
                        "Ciudad 1": {
                            "total": 500.25,
                            "pocs": {
                                "POC001 - Tienda A": {
                                    "total": 250.50,
                                    "w1": 50.25,
                                    "w2": 75.50,
                                    ...
                                },
                                ...
                            },
                            "w1": 100.5,
                            "w2": 150.75,
                            ...
                        },
                        ...
                    },
                    "total": 1500.75,
                    "w1": 300.25,
                    "w2": 450.50,
                    ...
                },
                "789012": { ... }
            }
        }
        """
        # Validar parámetro SKU (requerido) - puede ser uno o varios separados por comas
        sku_code_param = request.query_params.get('sku_code', '').strip()
        if not sku_code_param:
            return Response(
                {'error': 'Se requiere el parámetro sku_code'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Separar SKUs por comas y limpiar espacios
        sku_codes = [sku.strip()
                     for sku in sku_code_param.split(',') if sku.strip()]

        # Validar parámetros de fecha (requeridos)
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'Se requieren parámetros: start_date y end_date en formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date_obj = parse_date(start_date_str)
            end_date_obj = parse_date(end_date_str)

            if not start_date_obj or not end_date_obj:
                raise ValueError("Formato de fecha inválido")
        except (TypeError, ValueError):
            return Response(
                {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date_obj > end_date_obj:
            return Response(
                {'error': 'La fecha inicial no puede ser mayor que la fecha final'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar parámetro report_type (opcional)
        report_type = request.query_params.get(
            'report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Modo por fechas individuales (dates=true) o por semanas ISO (default)
        dates_mode = request.query_params.get('dates', 'false').strip().lower() == 'true'

        if dates_mode:
            periods_list = self._generate_dates_list(start_date_obj, end_date_obj)
            year_week_pairs = None
        else:
            weeks_info = self._generate_weeks_from_dates(start_date_obj, end_date_obj)
            if not weeks_info or not weeks_info['weeks_list']:
                return Response(
                    {'error': 'No se pudieron generar semanas para el rango especificado'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            periods_list = weeks_info['weeks_list']
            year_week_pairs = weeks_info['year_week_pairs']

        # Agrupar SKUs por nombre homologado
        sku_to_group, groups_info = _group_skus_by_homologated(sku_codes)

        # Obtener datos de ventas de los SKUs
        sales_data = self._get_sales_data(
            sku_codes, year_week_pairs, report_type, sku_to_group,
            dates_mode=dates_mode, start_date=start_date_obj, end_date=end_date_obj
        )

        if not sales_data or not sales_data.get('skus'):
            return Response(
                {'error': f'No se encontraron datos para los SKUs especificados en el rango indicado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir respuesta estructurada
        response_data = self._build_response(
            sales_data, periods_list, groups_info, dates_mode=dates_mode)

        # Crear log de la consulta
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='SKU_DETAIL_CITY_POC',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'sku_codes': sku_codes,
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': report_type,
                    'dates_mode': dates_mode
                },
                records_returned=len(sales_data.get('skus', {}))
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        return Response(response_data, status=status.HTTP_200_OK)

    def _generate_weeks_from_dates(self, start_date, end_date):
        """
        Generar lista de semanas y pares (año, semana) desde un rango de fechas.
        """
        year_week_set = set()
        current_date = start_date

        while current_date <= end_date:
            iso_calendar = current_date.isocalendar()
            year = iso_calendar[0]
            week = iso_calendar[1]
            year_week_set.add((year, week))
            current_date += timedelta(days=1)

        if not year_week_set:
            return None

        year_week_pairs = sorted(year_week_set, key=lambda x: (x[0], x[1]))
        weeks_list = [f"w{week}" for year, week in year_week_pairs]

        return {
            'weeks_list': weeks_list,
            'year_week_pairs': year_week_pairs
        }

    def _generate_dates_list(self, start_date, end_date):
        """
        Generar lista de fechas individuales en formato YYYY-MM-DD desde un rango.
        Se usa cuando dates=true en el request.
        """
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(str(current))
            current += timedelta(days=1)
        return dates

    def _get_sales_data(self, sku_codes, year_week_pairs, report_type='hectolitros', sku_to_group=None, dates_mode=False, start_date=None, end_date=None):
        """
        Obtener datos de ventas de uno o más SKUs agrupados por SKU, ciudad y POC.

        Args:
            sku_codes: Lista de códigos de SKU a consultar
            year_week_pairs: Lista de tuplas (año, semana). Ignorado cuando dates_mode=True.
            report_type: 'hectolitros' o 'caja'
            dates_mode: Si True, agrupa por fecha individual en lugar de semana ISO.
            start_date/end_date: Requeridos cuando dates_mode=True.

        Returns:
            dict: sku -> city -> poc -> {key: value}
            key es (year, week) en modo semana, o 'YYYY-MM-DD' en modo fecha.
        """
        # Construir filtro base
        if dates_mode:
            filters = Q(
                deleted_at__isnull=True,
                poc_city__isnull=False,
                poc_id__isnull=False,
                date__gte=start_date,
                date__lte=end_date
            )
        else:
            filters = Q(
                deleted_at__isnull=True,
                year__isnull=False,
                week__isnull=False,
                poc_city__isnull=False,
                poc_id__isnull=False
            )

        # Agregar filtro para múltiples SKUs (case-insensitive)
        sku_filter = Q()
        for sku_code in sku_codes:
            sku_filter |= Q(sku_vtex__iexact=sku_code)
        filters &= sku_filter

        # Filtro específico según el tipo de reporte
        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:  # caja
            filters &= Q(
                orders__isnull=False,
                units_assigned__isnull=False,
                unidades_por_caja__isnull=False,
                unidades_por_caja__gt=0  # Evitar división por cero
            )

        if not dates_mode:
            # Filtrar por pares (año, semana) específicos
            year_week_filter = Q()
            for year, week in year_week_pairs:
                year_week_filter |= Q(year=year, week=week)
            filters &= year_week_filter

        # Campos de agrupación según modo
        if dates_mode:
            grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                               'name_homologated', 'name', 'date']
            order_fields = ['sku_vtex', 'poc_city', 'poc_id', 'date']
        else:
            grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                               'name_homologated', 'name', 'year', 'week']
            order_fields = ['sku_vtex', 'poc_city', 'poc_id', 'year', 'week']

        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by(*order_fields)
        else:  # caja
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) /
                        F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
            ).order_by(*order_fields)

        # Organizar datos en estructura anidada
        # Modo semana: sku -> city -> poc -> {(year, week): value}
        # Modo fecha:  sku -> city -> poc -> {'YYYY-MM-DD': value}
        data_structure = {
            'skus': defaultdict(lambda: {
                'product_name': None,
                'cities': defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
            })
        }

        for item in sales_queryset:
            sku = item['sku_vtex']
            group_key = sku_to_group.get(sku, sku) if sku_to_group else sku

            if not data_structure['skus'][group_key]['product_name']:
                data_structure['skus'][group_key]['product_name'] = item['name_homologated'] or item['name'] or 'Sin nombre'

            city = item['poc_city'] or 'Sin ciudad'
            poc_id = item['poc_id'] or 'Sin ID'
            poc_name = item['poc_name'] or 'Sin nombre'
            poc_key = f"{poc_id} - {poc_name}"
            value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')

            if dates_mode:
                period_key = str(item['date'])
            else:
                period_key = (item['year'], item['week'])

            data_structure['skus'][group_key]['cities'][city][poc_key][period_key] += value

        return data_structure

    def _build_response(self, sales_data, periods_list, groups_info=None, dates_mode=False):
        """
        Construir respuesta JSON estructurada por SKUs/grupos, ciudades y POCs.
        periods_list contiene claves 'wN' (modo semana) o 'YYYY-MM-DD' (modo fecha).
        """
        skus_data = sales_data.get('skus', {})

        response = {
            'skus': {}
        }

        # Procesar cada SKU/grupo
        for group_key, sku_info in skus_data.items():
            product_name = sku_info.get(
                'product_name', 'Producto no encontrado')
            cities_data = sku_info.get('cities', {})

            group_data = groups_info.get(group_key, {}) if groups_info else {}

            sku_response = {
                'sku_codes': group_data.get('sku_codes', [group_key]),
                'product_name': group_data.get('product_name', product_name),
                'homologated': group_data.get('homologated', False),
                'cities': {},
                'total': 0
            }

            for period_id in periods_list:
                sku_response[period_id] = 0

            for city, pocs_data in cities_data.items():
                city_response = {
                    'total': 0,
                    'pocs': {}
                }

                for period_id in periods_list:
                    city_response[period_id] = 0

                for poc_key, periods_data in pocs_data.items():
                    poc_response = {
                        'total': 0
                    }

                    for period_id in periods_list:
                        if dates_mode:
                            # Clave directa por fecha 'YYYY-MM-DD'
                            period_value = periods_data.get(period_id, Decimal('0'))
                        else:
                            # Clave (year, week) — buscar por número de semana
                            week_num = int(period_id[1:])  # Remover 'w'
                            period_value = Decimal('0')
                            for (year, week), value in periods_data.items():
                                if week == week_num:
                                    period_value += value

                        poc_response[period_id] = round(float(period_value), 2)
                        poc_response['total'] += period_value

                        city_response[period_id] += period_value
                        city_response['total'] += period_value

                        sku_response[period_id] += period_value
                        sku_response['total'] += period_value

                    poc_response['total'] = round(
                        float(poc_response['total']), 2)
                    city_response['pocs'][poc_key] = poc_response

                city_response['total'] = round(
                    float(city_response['total']), 2)
                for period_id in periods_list:
                    city_response[period_id] = round(
                        float(city_response[period_id]), 2)

                sku_response['cities'][city] = city_response

            sku_response['total'] = round(float(sku_response['total']), 2)
            for period_id in periods_list:
                sku_response[period_id] = round(float(sku_response[period_id]), 2)

            response['skus'][group_key] = sku_response

        return response


class SKUDetailByCityPOCWeeklyReportDownloadView(APIView):
    """
    Vista para descargar el detalle de un SKU específico agrupado por ciudad y POC en Excel.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar detalle de ventas de uno o más SKUs en Excel.

        Query params:
        - sku_code: Código(s) del SKU a consultar (requerido). Puede ser uno o varios separados por comas
        - start_date: Fecha inicial en formato YYYY-MM-DD (requerido)
        - end_date: Fecha final en formato YYYY-MM-DD (requerido)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)

        Returns:
        Archivo Excel con el reporte estructurado por SKUs, ciudades y POCs
        """
        # Validar parámetro SKU (requerido) - puede ser uno o varios separados por comas
        sku_code_param = request.query_params.get('sku_code', '').strip()
        if not sku_code_param:
            return Response(
                {'error': 'Se requiere el parámetro sku_code'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Separar SKUs por comas y limpiar espacios
        sku_codes = [sku.strip()
                     for sku in sku_code_param.split(',') if sku.strip()]

        # Validar parámetros de fecha (requeridos)
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'Se requieren parámetros: start_date y end_date en formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date_obj = parse_date(start_date_str)
            end_date_obj = parse_date(end_date_str)

            if not start_date_obj or not end_date_obj:
                raise ValueError("Formato de fecha inválido")
        except (TypeError, ValueError):
            return Response(
                {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_date_obj > end_date_obj:
            return Response(
                {'error': 'La fecha inicial no puede ser mayor que la fecha final'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar parámetro report_type (opcional)
        report_type = request.query_params.get(
            'report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Modo por fechas individuales (dates=true) o por semanas ISO (default)
        dates_mode = request.query_params.get('dates', 'false').strip().lower() == 'true'

        if dates_mode:
            periods_list = self._generate_dates_list(start_date_obj, end_date_obj)
            year_week_pairs = None
        else:
            weeks_info = self._generate_weeks_from_dates(start_date_obj, end_date_obj)
            if not weeks_info or not weeks_info['weeks_list']:
                return Response(
                    {'error': 'No se pudieron generar semanas para el rango especificado'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            periods_list = weeks_info['weeks_list']
            year_week_pairs = weeks_info['year_week_pairs']

        # Agrupar SKUs por nombre homologado
        sku_to_group, groups_info = _group_skus_by_homologated(sku_codes)

        # Obtener datos de ventas de los SKUs
        sales_data = self._get_sales_data(
            sku_codes, year_week_pairs, report_type, sku_to_group,
            dates_mode=dates_mode, start_date=start_date_obj, end_date=end_date_obj
        )

        if not sales_data or not sales_data.get('skus'):
            return Response(
                {'error': f'No se encontraron datos para los SKUs especificados en el rango indicado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir respuesta estructurada
        response_data = self._build_response(
            sales_data, periods_list, groups_info, dates_mode=dates_mode)

        # Crear DataFrame para Excel
        df = self._build_excel_dataframe(response_data, periods_list)

        # Crear log de la descarga
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='SKU_DETAIL_CITY_POC_DOWNLOAD',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'sku_codes': sku_codes,
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': report_type,
                    'dates_mode': dates_mode
                },
                records_returned=len(df)
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        # Generar archivo Excel
        output = BytesIO()
        sheet_name = 'SKUs' if len(sku_codes) > 1 else f'SKU {sku_codes[0]}'
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            # Ajustar ancho de columnas
            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df.columns, 1):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(str(col))
                )
                worksheet.column_dimensions[chr(
                    64 + idx)].width = min(max_length + 2, 50)

        output.seek(0)

        # Generar nombre de archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        type_label = 'hectolitros' if report_type == 'hectolitros' else 'cajas'
        sku_label = sku_codes[0] if len(
            sku_codes) == 1 else f'{len(sku_codes)}_skus'
        filename = f'sku_detail_{sku_label}_{type_label}_{start_date_str}_{end_date_str}_{timestamp}.xlsx'

        # Crear respuesta HTTP
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _generate_weeks_from_dates(self, start_date, end_date):
        """Generar lista de semanas y pares (año, semana) desde un rango de fechas."""
        year_week_set = set()
        current_date = start_date

        while current_date <= end_date:
            iso_calendar = current_date.isocalendar()
            year = iso_calendar[0]
            week = iso_calendar[1]
            year_week_set.add((year, week))
            current_date += timedelta(days=1)

        if not year_week_set:
            return None

        year_week_pairs = sorted(year_week_set, key=lambda x: (x[0], x[1]))
        weeks_list = [f"w{week}" for year, week in year_week_pairs]

        return {
            'weeks_list': weeks_list,
            'year_week_pairs': year_week_pairs
        }

    def _generate_dates_list(self, start_date, end_date):
        """
        Generar lista de fechas individuales en formato YYYY-MM-DD desde un rango.
        Se usa cuando dates=true en el request.
        """
        dates = []
        current = start_date
        while current <= end_date:
            dates.append(str(current))
            current += timedelta(days=1)
        return dates

    def _get_sales_data(self, sku_codes, year_week_pairs, report_type='hectolitros', sku_to_group=None, dates_mode=False, start_date=None, end_date=None):
        """Obtener datos de ventas de uno o más SKUs."""
        # Construir filtro base
        if dates_mode:
            filters = Q(
                deleted_at__isnull=True,
                poc_city__isnull=False,
                poc_id__isnull=False,
                date__gte=start_date,
                date__lte=end_date
            )
        else:
            filters = Q(
                deleted_at__isnull=True,
                year__isnull=False,
                week__isnull=False,
                poc_city__isnull=False,
                poc_id__isnull=False
            )

        # Agregar filtro para SKUs (case-insensitive)
        sku_filter = Q()
        for sku_code in sku_codes:
            sku_filter |= Q(sku_vtex__iexact=sku_code)
        filters &= sku_filter

        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:
            filters &= Q(
                orders__isnull=False,
                units_assigned__isnull=False,
                unidades_por_caja__isnull=False,
                unidades_por_caja__gt=0  # Evitar división por cero
            )

        if not dates_mode:
            year_week_filter = Q()
            for year, week in year_week_pairs:
                year_week_filter |= Q(year=year, week=week)
            filters &= year_week_filter

        # Campos de agrupación según modo
        if dates_mode:
            grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                               'name_homologated', 'name', 'date']
            order_fields = ['sku_vtex', 'poc_city', 'poc_id', 'date']
        else:
            grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                               'name_homologated', 'name', 'year', 'week']
            order_fields = ['sku_vtex', 'poc_city', 'poc_id', 'year', 'week']

        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by(*order_fields)
        else:
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) /
                        F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
            ).order_by(*order_fields)

        # Estructura para múltiples SKUs
        data_structure = {
            'skus': defaultdict(lambda: {
                'product_name': None,
                'cities': defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
            })
        }

        for item in sales_queryset:
            sku = item['sku_vtex']
            group_key = sku_to_group.get(sku, sku) if sku_to_group else sku

            if not data_structure['skus'][group_key]['product_name']:
                data_structure['skus'][group_key]['product_name'] = item['name_homologated'] or item['name'] or 'Sin nombre'

            city = item['poc_city'] or 'Sin ciudad'
            poc_id = item['poc_id'] or 'Sin ID'
            poc_name = item['poc_name'] or 'Sin nombre'
            poc_key = f"{poc_id} - {poc_name}"
            value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')

            if dates_mode:
                period_key = str(item['date'])
            else:
                period_key = (item['year'], item['week'])

            data_structure['skus'][group_key]['cities'][city][poc_key][period_key] += value

        return data_structure

    def _build_response(self, sales_data, periods_list, groups_info=None, dates_mode=False):
        """Construir respuesta JSON estructurada para múltiples SKUs/grupos."""
        response = {'skus': {}}
        skus_data = sales_data.get('skus', {})

        for group_key, sku_data in skus_data.items():
            product_name = sku_data.get(
                'product_name', 'Producto no encontrado')
            cities_data = sku_data.get('cities', {})

            group_data = groups_info.get(group_key, {}) if groups_info else {}

            sku_response = {
                'sku_codes': group_data.get('sku_codes', [group_key]),
                'product_name': group_data.get('product_name', product_name),
                'homologated': group_data.get('homologated', False),
                'cities': {},
                'total': 0
            }

            for period_id in periods_list:
                sku_response[period_id] = 0

            for city, pocs_data in cities_data.items():
                city_response = {
                    'total': 0,
                    'pocs': {}
                }

                for period_id in periods_list:
                    city_response[period_id] = 0

                for poc_key, periods_data in pocs_data.items():
                    poc_response = {'total': 0}

                    for period_id in periods_list:
                        if dates_mode:
                            period_value = periods_data.get(period_id, Decimal('0'))
                        else:
                            week_num = int(period_id[1:])
                            period_value = Decimal('0')
                            for (year, week), value in periods_data.items():
                                if week == week_num:
                                    period_value += value

                        poc_response[period_id] = round(float(period_value), 2)
                        poc_response['total'] += period_value
                        city_response[period_id] += period_value
                        city_response['total'] += period_value
                        sku_response[period_id] += period_value
                        sku_response['total'] += period_value

                    poc_response['total'] = round(
                        float(poc_response['total']), 2)
                    city_response['pocs'][poc_key] = poc_response

                city_response['total'] = round(
                    float(city_response['total']), 2)
                for period_id in periods_list:
                    city_response[period_id] = round(
                        float(city_response[period_id]), 2)

                sku_response['cities'][city] = city_response

            sku_response['total'] = round(float(sku_response['total']), 2)
            for period_id in periods_list:
                sku_response[period_id] = round(float(sku_response[period_id]), 2)

            response['skus'][group_key] = sku_response

        return response

    def _build_excel_dataframe(self, response_data, periods_list):
        """Construir DataFrame para exportar a Excel."""
        rows = []
        skus_data = response_data.get('skus', {})

        for group_key, sku_info in skus_data.items():
            product_name = sku_info.get(
                'product_name', 'Producto no encontrado')
            sku_codes_str = ', '.join(sku_info.get('sku_codes', [group_key]))
            cities_data = sku_info.get('cities', {})

            for city, city_data in cities_data.items():
                for poc_key, poc_data in city_data.get('pocs', {}).items():
                    row = {
                        'SKU': sku_codes_str,
                        'Producto': product_name,
                        'Ciudad': city,
                        'POC': poc_key,
                        'Total': poc_data.get('total', 0)
                    }

                    # Agregar columnas de periodos (semanas o fechas)
                    for period_id in periods_list:
                        row[period_id.upper()] = poc_data.get(period_id, 0)

                    rows.append(row)

        df = pd.DataFrame(rows)

        # Ordenar por SKU, ciudad y total descendente
        if not df.empty:
            df = df.sort_values(['SKU', 'Ciudad', 'Total'],
                                ascending=[True, True, False])

        return df
