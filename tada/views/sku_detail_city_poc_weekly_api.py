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

from tada.models import SalesRecord, SalesRecordQueryLog
from tada.utils.constants import APPS


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
        sku_codes = [sku.strip() for sku in sku_code_param.split(',') if sku.strip()]

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

        # Generar información de semanas desde las fechas
        weeks_info = self._generate_weeks_from_dates(
            start_date_obj, end_date_obj)

        if not weeks_info or not weeks_info['weeks_list']:
            return Response(
                {'error': 'No se pudieron generar semanas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        weeks_list = weeks_info['weeks_list']
        year_week_pairs = weeks_info['year_week_pairs']

        # Obtener datos de ventas de los SKUs
        sales_data = self._get_sales_data(
            sku_codes, year_week_pairs, report_type
        )

        if not sales_data or not sales_data.get('skus'):
            return Response(
                {'error': f'No se encontraron datos para los SKUs especificados en el rango indicado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir respuesta estructurada
        response_data = self._build_response(sales_data, weeks_list)

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
                    'report_type': report_type
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

    def _get_sales_data(self, sku_codes, year_week_pairs, report_type='hectolitros'):
        """
        Obtener datos de ventas de uno o más SKUs agrupados por SKU, ciudad y POC.

        Args:
            sku_codes: Lista de códigos de SKU a consultar
            year_week_pairs: Lista de tuplas (año, semana)
            report_type: 'hectolitros' o 'caja'

        Returns:
            dict: {
                'skus': {
                    'sku_code': {
                        'product_name': str,
                        'cities': {
                            city: {
                                pocs: {
                                    poc_key: {(year, week): value}
                                }
                            }
                        }
                    }
                }
            }
        """
        # Construir filtro base (sin SKU aún)
        filters = Q(
            deleted_at__isnull=True,
            year__isnull=False,
            week__isnull=False,
            poc_city__isnull=False,
            poc_id__isnull=False
        )
        
        # Agregar filtro para múltiples SKUs (case-insensitive)
        # Usar OR con iexact para cada SKU individualmente
        sku_filter = Q()
        for sku_code in sku_codes:
            sku_filter |= Q(sku_vtex__iexact=sku_code)
        filters &= sku_filter

        # Filtro específico según el tipo de reporte
        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:  # caja
            filters &= Q(orders__isnull=False, units_assigned__isnull=False,
                         unidades_por_caja__isnull=False)

        # Filtrar por pares (año, semana) específicos
        year_week_filter = Q()
        for year, week in year_week_pairs:
            year_week_filter |= Q(year=year, week=week)
        filters &= year_week_filter
        # Obtener datos agrupados con anotación según tipo de reporte
        grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                           'name_homologated', 'name', 'year', 'week']

        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by('poc_city', 'poc_id', 'year', 'week')
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
            ).order_by('sku_vtex', 'poc_city', 'poc_id', 'year', 'week')

        # Organizar datos en estructura anidada: sku -> city -> poc -> (year, week) -> value
        data_structure = {
            'skus': defaultdict(lambda: {
                'product_name': None,
                'cities': defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
            })
        }

        for item in sales_queryset:
            sku = item['sku_vtex']
            
            # Capturar nombre del producto (solo una vez por SKU)
            if not data_structure['skus'][sku]['product_name']:
                data_structure['skus'][sku]['product_name'] = item['name_homologated'] or item['name'] or 'Sin nombre'

            city = item['poc_city'] or 'Sin ciudad'
            poc_id = item['poc_id'] or 'Sin ID'
            poc_name = item['poc_name'] or 'Sin nombre'
            poc_key = f"{poc_id} - {poc_name}"
            year = item['year']
            week = item['week']
            value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')

            data_structure['skus'][sku]['cities'][city][poc_key][(year, week)] = value

        return data_structure

    def _build_response(self, sales_data, weeks_list):
        """
        Construir respuesta JSON estructurada por SKUs, ciudades y POCs.
        """
        skus_data = sales_data.get('skus', {})
        
        response = {
            'skus': {}
        }

        # Procesar cada SKU
        for sku_code, sku_info in skus_data.items():
            product_name = sku_info.get('product_name', 'Producto no encontrado')
            cities_data = sku_info.get('cities', {})
            
            sku_response = {
                'sku_code': sku_code,
                'product_name': product_name,
                'cities': {},
                'total': 0
            }
            
            # Inicializar totales por semana a nivel de SKU
            for week_id in weeks_list:
                sku_response[week_id] = 0

            # Procesar cada ciudad
            for city, pocs_data in cities_data.items():
                city_response = {
                    'total': 0,
                    'pocs': {}
                }

                # Inicializar totales por semana a nivel ciudad
                for week_id in weeks_list:
                    city_response[week_id] = 0

                # Procesar cada POC en la ciudad
                for poc_key, weeks_data in pocs_data.items():
                    poc_response = {
                        'total': 0
                    }

                    # Agregar datos por semana para el POC
                    for week_id in weeks_list:
                        week_num = int(week_id[1:])  # Remover 'w'

                        # Buscar el valor en weeks_data
                        week_value = Decimal('0')
                        for (year, week), value in weeks_data.items():
                            if week == week_num:
                                week_value += value

                        poc_response[week_id] = round(float(week_value), 2)
                        poc_response['total'] += week_value

                        # Acumular en ciudad
                        city_response[week_id] += week_value
                        city_response['total'] += week_value

                        # Acumular en total del SKU
                        sku_response[week_id] += week_value
                        sku_response['total'] += week_value

                    # Redondear total del POC
                    poc_response['total'] = round(float(poc_response['total']), 2)
                    city_response['pocs'][poc_key] = poc_response
                # Redondear totales de ciudad y convertir a float
                city_response['total'] = round(float(city_response['total']), 2)
                for week_id in weeks_list:
                    city_response[week_id] = round(
                        float(city_response[week_id]), 2)

                sku_response['cities'][city] = city_response

            # Redondear totales del SKU
            sku_response['total'] = round(float(sku_response['total']), 2)
            for week_id in weeks_list:
                sku_response[week_id] = round(float(sku_response[week_id]), 2)
            
            response['skus'][sku_code] = sku_response

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
        sku_codes = [sku.strip() for sku in sku_code_param.split(',') if sku.strip()]

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

        # Generar información de semanas desde las fechas
        weeks_info = self._generate_weeks_from_dates(
            start_date_obj, end_date_obj)

        if not weeks_info or not weeks_info['weeks_list']:
            return Response(
                {'error': 'No se pudieron generar semanas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        weeks_list = weeks_info['weeks_list']
        year_week_pairs = weeks_info['year_week_pairs']

        # Obtener datos de ventas de los SKUs
        sales_data = self._get_sales_data(
            sku_codes, year_week_pairs, report_type
        )

        if not sales_data or not sales_data.get('skus'):
            return Response(
                {'error': f'No se encontraron datos para los SKUs especificados en el rango indicado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Construir respuesta estructurada
        response_data = self._build_response(sales_data, weeks_list)

        # Crear DataFrame para Excel
        df = self._build_excel_dataframe(response_data, weeks_list)

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
                    'report_type': report_type
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
        sku_label = sku_codes[0] if len(sku_codes) == 1 else f'{len(sku_codes)}_skus'
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

    def _get_sales_data(self, sku_codes, year_week_pairs, report_type='hectolitros'):
        """Obtener datos de ventas de uno o más SKUs."""
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
            filters &= Q(orders__isnull=False, units_assigned__isnull=False,
                         unidades_por_caja__isnull=False)

        year_week_filter = Q()
        for year, week in year_week_pairs:
            year_week_filter |= Q(year=year, week=week)
        filters &= year_week_filter

        # Incluir sku_vtex en los campos de agrupación
        grouping_fields = ['sku_vtex', 'poc_city', 'poc_id', 'poc_name',
                           'name_homologated', 'name', 'year', 'week']

        if report_type == 'hectolitros':
            sales_queryset = SalesRecord.objects.filter(filters).values(
                *grouping_fields
            ).annotate(
                total_value=Sum('hectolitros')
            ).order_by('sku_vtex', 'poc_city', 'poc_id', 'year', 'week')
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
            ).order_by('sku_vtex', 'poc_city', 'poc_id', 'year', 'week')

        # Estructura para múltiples SKUs
        data_structure = {
            'skus': defaultdict(lambda: {
                'product_name': None,
                'cities': defaultdict(lambda: defaultdict(lambda: defaultdict(Decimal)))
            })
        }

        for item in sales_queryset:
            sku_code = item['sku_vtex']
            
            # Establecer nombre del producto si no existe
            if not data_structure['skus'][sku_code]['product_name']:
                data_structure['skus'][sku_code]['product_name'] = item['name_homologated'] or item['name'] or 'Sin nombre'

            city = item['poc_city'] or 'Sin ciudad'
            poc_id = item['poc_id'] or 'Sin ID'
            poc_name = item['poc_name'] or 'Sin nombre'
            poc_key = f"{poc_id} - {poc_name}"
            year = item['year']
            week = item['week']
            value = Decimal(str(item['total_value'])) if item['total_value'] else Decimal('0')

            data_structure['skus'][sku_code]['cities'][city][poc_key][(year, week)] = value

        return data_structure

    def _build_response(self, sales_data, weeks_list):
        """Construir respuesta JSON estructurada para múltiples SKUs."""
        response = {'skus': {}}
        skus_data = sales_data.get('skus', {})

        for sku_code, sku_data in skus_data.items():
            product_name = sku_data.get('product_name', 'Producto no encontrado')
            cities_data = sku_data.get('cities', {})

            sku_response = {
                'product_name': product_name,
                'cities': {},
                'total': 0
            }

            for week_id in weeks_list:
                sku_response[week_id] = 0

            for city, pocs_data in cities_data.items():
                city_response = {
                    'total': 0,
                    'pocs': {}
                }

                for week_id in weeks_list:
                    city_response[week_id] = 0

                for poc_key, weeks_data in pocs_data.items():
                    poc_response = {'total': 0}

                    for week_id in weeks_list:
                        week_num = int(week_id[1:])
                        week_value = Decimal('0')
                        for (year, week), value in weeks_data.items():
                            if week == week_num:
                                week_value += value

                        poc_response[week_id] = round(float(week_value), 2)
                        poc_response['total'] += week_value
                        city_response[week_id] += week_value
                        city_response['total'] += week_value
                        sku_response[week_id] += week_value
                        sku_response['total'] += week_value

                    poc_response['total'] = round(float(poc_response['total']), 2)
                    city_response['pocs'][poc_key] = poc_response

                city_response['total'] = round(float(city_response['total']), 2)
                for week_id in weeks_list:
                    city_response[week_id] = round(float(city_response[week_id]), 2)

                sku_response['cities'][city] = city_response

            sku_response['total'] = round(float(sku_response['total']), 2)
            for week_id in weeks_list:
                sku_response[week_id] = round(float(sku_response[week_id]), 2)
            
            response['skus'][sku_code] = sku_response

        return response

    def _build_excel_dataframe(self, response_data, weeks_list):
        """Construir DataFrame para exportar a Excel."""
        rows = []
        skus_data = response_data.get('skus', {})

        for sku_code, sku_info in skus_data.items():
            product_name = sku_info.get('product_name', 'Producto no encontrado')
            cities_data = sku_info.get('cities', {})
            
            for city, city_data in cities_data.items():
                for poc_key, poc_data in city_data.get('pocs', {}).items():
                    row = {
                        'SKU': sku_code,
                        'Producto': product_name,
                        'Ciudad': city,
                        'POC': poc_key,
                        'Total': poc_data.get('total', 0)
                    }

                    # Agregar columnas de semanas
                    for week_id in weeks_list:
                        row[week_id.upper()] = poc_data.get(week_id, 0)

                    rows.append(row)

        df = pd.DataFrame(rows)

        # Ordenar por SKU, ciudad y total descendente
        if not df.empty:
            df = df.sort_values(['SKU', 'Ciudad', 'Total'], ascending=[True, True, False])

        return df
