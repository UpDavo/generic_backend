from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta
from django.db.models import Sum, Q, F, DecimalField, ExpressionWrapper
from collections import defaultdict, OrderedDict
from decimal import Decimal
from io import BytesIO
import pandas as pd

from tada.models import SalesRecord, SalesRecordQueryLog
from tada.utils.constants import APPS

# Nombres de días en español
DAY_NAMES_ES = {
    0: 'Lunes',
    1: 'Martes',
    2: 'Miércoles',
    3: 'Jueves',
    4: 'Viernes',
    5: 'Sábado',
    6: 'Domingo',
}


class VentaHectoPorPocView(APIView):
    """
    Endpoint que retorna ventas (hectolitros o cajas) agrupadas por POC y fecha.

    Query params:
    - start_date: Fecha inicial en formato YYYY-MM-DD (requerido)
    - end_date: Fecha final en formato YYYY-MM-DD (requerido)
    - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)
    - group_by_city: "true" o "false" (opcional, default: false). Agrupa los POCs dentro de su ciudad.

    Respuesta sin group_by_city:
    {
        "POC_NAME": {
            "2026-01-15": {
                "hectolitros": 19234.0,
                "nombre_dia": "Jueves"
            }
        }
    }

    Respuesta con group_by_city=true:
    {
        "Ciudad A": {
            "POC_NAME": {
                "2026-01-15": {
                    "hectolitros": 19234.0,
                    "nombre_dia": "Jueves"
                }
            },
            "POC_NAME_2": { ... }
        },
        "Ciudad B": { ... }
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # --- Validar parámetros de fecha ---
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'Se requieren parámetros: start_date y end_date en formato YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_date_obj = parse_date(start_date_str)
            end_date_obj = parse_date(end_date_str)
            if not start_date_obj or not end_date_obj:
                raise ValueError("Formato de fecha inválido")
        except (TypeError, ValueError):
            return Response(
                {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if start_date_obj > end_date_obj:
            return Response(
                {'error': 'La fecha inicial no puede ser mayor que la fecha final'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validar report_type ---
        report_type = request.query_params.get(
            'report_type', 'hectolitros'
        ).strip().lower()

        if report_type not in ('hectolitros', 'caja'):
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Validar group_by_city ---
        group_by_city = request.query_params.get(
            'group_by_city', 'false'
        ).strip().lower() in ('true', '1', 'yes')

        # --- Construir queryset ---
        value_field_label = report_type  # "hectolitros" o "caja"

        filters = Q(
            deleted_at__isnull=True,
            date__gte=start_date_obj,
            date__lte=end_date_obj,
            poc_name__isnull=False,
        )

        if report_type == 'hectolitros':
            filters &= Q(hectolitros__isnull=False)
        else:
            filters &= Q(
                orders__isnull=False,
                units_assigned__isnull=False,
                unidades_por_caja__isnull=False,
                unidades_por_caja__gt=0,
            )

        grouping_fields = ['poc_name', 'date']
        order_fields = ['poc_name', 'date']

        if group_by_city:
            grouping_fields = ['poc_city', 'poc_name', 'date']
            order_fields = ['poc_city', 'poc_name', 'date']

        if report_type == 'hectolitros':
            qs = (
                SalesRecord.objects
                .filter(filters)
                .values(*grouping_fields)
                .annotate(total_value=Sum('hectolitros'))
                .order_by(*order_fields)
            )
        else:
            qs = (
                SalesRecord.objects
                .filter(filters)
                .values(*grouping_fields)
                .annotate(
                    total_value=Sum(
                        ExpressionWrapper(
                            (F('orders') * F('units_assigned')) /
                            F('unidades_por_caja'),
                            output_field=DecimalField(),
                        )
                    )
                )
                .order_by(*order_fields)
            )

        # --- Construir respuesta ---
        if group_by_city:
            result = defaultdict(lambda: defaultdict(lambda: OrderedDict()))
            for item in qs:
                city = item['poc_city'] or 'Sin ciudad'
                poc_name = item['poc_name'] or 'Sin nombre'
                record_date = item['date']
                value = round(float(item['total_value']),
                              2) if item['total_value'] else 0.0
                day_name = DAY_NAMES_ES.get(record_date.weekday(), '')
                date_key = record_date.strftime('%Y-%m-%d')
                result[city][poc_name][date_key] = {
                    value_field_label: value,
                    'nombre_dia': day_name,
                }
        else:
            result = defaultdict(lambda: OrderedDict())
            for item in qs:
                poc_name = item['poc_name'] or 'Sin nombre'
                record_date = item['date']
                value = round(float(item['total_value']),
                              2) if item['total_value'] else 0.0
                day_name = DAY_NAMES_ES.get(record_date.weekday(), '')
                date_key = record_date.strftime('%Y-%m-%d')
                result[poc_name][date_key] = {
                    value_field_label: value,
                    'nombre_dia': day_name,
                }

        if not result:
            return Response(
                {'error': 'No se encontraron datos para el rango de fechas indicado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Log de consulta ---
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='VENTA_HECTO_POR_POC',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': report_type,
                    'group_by_city': group_by_city,
                },
                records_returned=len(result),
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        return Response(result, status=status.HTTP_200_OK)


def _build_venta_hecto_queryset(start_date_obj, end_date_obj, report_type, group_by_city):
    """
    Lógica compartida para construir el queryset de venta hecto por POC.
    Retorna (qs, value_field_label).
    """
    value_field_label = report_type

    filters = Q(
        deleted_at__isnull=True,
        date__gte=start_date_obj,
        date__lte=end_date_obj,
        poc_name__isnull=False,
    )

    if report_type == 'hectolitros':
        filters &= Q(hectolitros__isnull=False)
    else:
        filters &= Q(
            orders__isnull=False,
            units_assigned__isnull=False,
            unidades_por_caja__isnull=False,
            unidades_por_caja__gt=0,
        )

    grouping_fields = ['poc_name', 'date']
    order_fields = ['poc_name', 'date']

    if group_by_city:
        grouping_fields = ['poc_city', 'poc_name', 'date']
        order_fields = ['poc_city', 'poc_name', 'date']

    if report_type == 'hectolitros':
        qs = (
            SalesRecord.objects
            .filter(filters)
            .values(*grouping_fields)
            .annotate(total_value=Sum('hectolitros'))
            .order_by(*order_fields)
        )
    else:
        qs = (
            SalesRecord.objects
            .filter(filters)
            .values(*grouping_fields)
            .annotate(
                total_value=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) /
                        F('unidades_por_caja'),
                        output_field=DecimalField(),
                    )
                )
            )
            .order_by(*order_fields)
        )

    return qs, value_field_label


def _parse_venta_hecto_params(request):
    """
    Parsear y validar parámetros comunes. Retorna dict con los valores o Response de error.
    """
    start_date_str = request.query_params.get('start_date')
    end_date_str = request.query_params.get('end_date')

    if not start_date_str or not end_date_str:
        return Response(
            {'error': 'Se requieren parámetros: start_date y end_date en formato YYYY-MM-DD'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        start_date_obj = parse_date(start_date_str)
        end_date_obj = parse_date(end_date_str)
        if not start_date_obj or not end_date_obj:
            raise ValueError("Formato de fecha inválido")
    except (TypeError, ValueError):
        return Response(
            {'error': 'Formato de fecha inválido. Use YYYY-MM-DD'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if start_date_obj > end_date_obj:
        return Response(
            {'error': 'La fecha inicial no puede ser mayor que la fecha final'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    report_type = request.query_params.get(
        'report_type', 'hectolitros'
    ).strip().lower()

    if report_type not in ('hectolitros', 'caja'):
        return Response(
            {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    group_by_city = request.query_params.get(
        'group_by_city', 'false'
    ).strip().lower() in ('true', '1', 'yes')

    return {
        'start_date_str': start_date_str,
        'end_date_str': end_date_str,
        'start_date_obj': start_date_obj,
        'end_date_obj': end_date_obj,
        'report_type': report_type,
        'group_by_city': group_by_city,
    }


class VentaHectoPorPocDownloadView(APIView):
    """
    Descargar el reporte de ventas (hectolitros o cajas) por POC y fecha en Excel.

    Query params:
    - start_date: Fecha inicial YYYY-MM-DD (requerido)
    - end_date: Fecha final YYYY-MM-DD (requerido)
    - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)
    - group_by_city: "true" o "false" (opcional, default: false)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        params = _parse_venta_hecto_params(request)
        if isinstance(params, Response):
            return params

        start_date_obj = params['start_date_obj']
        end_date_obj = params['end_date_obj']
        report_type = params['report_type']
        group_by_city = params['group_by_city']
        start_date_str = params['start_date_str']
        end_date_str = params['end_date_str']

        qs, value_field_label = _build_venta_hecto_queryset(
            start_date_obj, end_date_obj, report_type, group_by_city
        )

        # --- Recopilar todas las fechas únicas (para columnas) ---
        all_dates = sorted(set())
        rows = []

        for item in qs:
            record_date = item['date']
            all_dates_set = set()

        # Recorrer de nuevo para construir filas (materializar queryset)
        data_list = list(qs)

        if not data_list:
            return Response(
                {'error': 'No se encontraron datos para el rango de fechas indicado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Recopilar fechas únicas ordenadas
        all_dates = sorted({item['date'] for item in data_list})

        # Construir estructura intermedia para pivotar
        if group_by_city:
            # key = (city, poc_name)
            pivot = defaultdict(lambda: {})
            for item in data_list:
                city = item['poc_city'] or 'Sin ciudad'
                poc = item['poc_name'] or 'Sin nombre'
                d = item['date']
                val = round(float(item['total_value']),
                            2) if item['total_value'] else 0.0
                pivot[(city, poc)][d] = val

            for (city, poc), date_vals in sorted(pivot.items()):
                row = {'Ciudad': city, 'POC': poc}
                total = 0.0
                for d in all_dates:
                    date_key = d.strftime('%Y-%m-%d')
                    day_name = DAY_NAMES_ES.get(d.weekday(), '')
                    col_name = f"{date_key} ({day_name})"
                    v = date_vals.get(d, 0.0)
                    row[col_name] = v
                    total += v
                row['Total'] = round(total, 2)
                rows.append(row)
        else:
            pivot = defaultdict(lambda: {})
            for item in data_list:
                poc = item['poc_name'] or 'Sin nombre'
                d = item['date']
                val = round(float(item['total_value']),
                            2) if item['total_value'] else 0.0
                pivot[poc][d] = val

            for poc, date_vals in sorted(pivot.items()):
                row = {'POC': poc}
                total = 0.0
                for d in all_dates:
                    date_key = d.strftime('%Y-%m-%d')
                    day_name = DAY_NAMES_ES.get(d.weekday(), '')
                    col_name = f"{date_key} ({day_name})"
                    v = date_vals.get(d, 0.0)
                    row[col_name] = v
                    total += v
                row['Total'] = round(total, 2)
                rows.append(row)

        df = pd.DataFrame(rows)

        # Reordenar columnas: fijas primero, luego fechas, luego Total
        fixed_cols = ['Ciudad', 'POC'] if group_by_city else ['POC']
        date_cols = [
            c for c in df.columns if c not in fixed_cols and c != 'Total']
        df = df[fixed_cols + date_cols + ['Total']]

        # Ordenar por Ciudad (si aplica) y Total descendente
        sort_cols = ['Ciudad', 'Total'] if group_by_city else ['Total']
        sort_asc = [True, False] if group_by_city else [False]
        df = df.sort_values(sort_cols, ascending=sort_asc)

        # --- Log ---
        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='VENTA_HECTO_POR_POC_DOWNLOAD',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': report_type,
                    'group_by_city': group_by_city,
                },
                records_returned=len(df),
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        # --- Generar Excel ---
        output = BytesIO()
        type_label = 'hectolitros' if report_type == 'hectolitros' else 'cajas'
        sheet_name = f'Venta {type_label} por POC'

        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)

            worksheet = writer.sheets[sheet_name]
            for idx, col in enumerate(df.columns, 1):
                max_length = max(
                    df[col].astype(str).apply(len).max(),
                    len(str(col))
                )
                from openpyxl.utils import get_column_letter
                worksheet.column_dimensions[get_column_letter(
                    idx)].width = min(max_length + 2, 30)

        output.seek(0)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'venta_{type_label}_por_poc_{start_date_str}_{end_date_str}_{timestamp}.xlsx'

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
