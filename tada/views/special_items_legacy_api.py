from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from django.db.models import Q
from datetime import datetime
from collections import defaultdict
from decimal import Decimal
from io import BytesIO
import pandas as pd

from tada.models import SpecialItemsLegacy, SalesRecordQueryLog
from tada.utils.constants import APPS


class SpecialItemsLegacyListView(APIView):
    """
    Endpoint para obtener todos los ítems especiales legacy filtrados por rango de mes/día,
    agrupados por nombre de producto. Devuelve registros de TODOS los años en el rango,
    permitiendo comparar 2022, 2023, 2026, etc.

    Query params:
    - start_md: Mes y día inicial en formato MM-DD (requerido), ej: 01-15
    - end_md:   Mes y día final   en formato MM-DD (requerido), ej: 03-09

    Respuesta:
    {
        "count": 3,
        "results": {
            "Producto A": {
                "total_hectolitros": 125.5,
                "total_cajas": 300.0,
                "records": [
                    {"id": 1, "fecha": "2022-01-15", "hectolitros": "12.5000", "cajas": "30.0000"},
                    {"id": 2, "fecha": "2026-01-15", "hectolitros": "14.0000", "cajas": "35.0000"},
                    ...
                ]
            },
            ...
        }
    }
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # --- Validar parámetros de mes/día ---
        start_md = request.query_params.get('start_md')
        end_md = request.query_params.get('end_md')

        if not start_md or not end_md:
            return Response(
                {'error': 'Se requieren parámetros: start_md y end_md en formato MM-DD (ej: 01-15)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_month, start_day = int(start_md.split('-')[0]), int(start_md.split('-')[1])
            end_month, end_day = int(end_md.split('-')[0]), int(end_md.split('-')[1])
            if not (1 <= start_month <= 12 and 1 <= start_day <= 31):
                raise ValueError
            if not (1 <= end_month <= 12 and 1 <= end_day <= 31):
                raise ValueError
        except (ValueError, IndexError, AttributeError):
            return Response(
                {'error': 'Formato inválido. Use MM-DD (ej: 01-15)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (start_month, start_day) > (end_month, end_day):
            return Response(
                {'error': 'El inicio (start_md) no puede ser mayor que el fin (end_md)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Filtrar por mes/día ignorando el año ---
        q_after_start = (
            Q(fecha__month=start_month, fecha__day__gte=start_day) |
            Q(fecha__month__gt=start_month)
        )
        q_before_end = (
            Q(fecha__month=end_month, fecha__day__lte=end_day) |
            Q(fecha__month__lt=end_month)
        )
        qs = SpecialItemsLegacy.objects.filter(
            q_after_start & q_before_end,
            is_active=True,
        ).order_by('nombre', 'fecha')

        # Agrupar por nombre de producto
        grouped = defaultdict(lambda: {
            'total_hectolitros': Decimal('0'),
            'total_cajas': Decimal('0'),
            'records': []
        })

        for item in qs.values('id', 'fecha', 'nombre', 'hectolitros', 'cajas'):
            nombre = item['nombre']
            grouped[nombre]['total_hectolitros'] += item['hectolitros'] or Decimal('0')
            grouped[nombre]['total_cajas'] += item['cajas'] or Decimal('0')
            grouped[nombre]['records'].append({
                'id': item['id'],
                'fecha': str(item['fecha']),
                'hectolitros': item['hectolitros'],
                'cajas': item['cajas'],
            })

        # Convertir totales a float para serialización
        results = {
            nombre: {
                'total_hectolitros': round(float(data['total_hectolitros']), 4),
                'total_cajas': round(float(data['total_cajas']), 4),
                'records': data['records'],
            }
            for nombre, data in grouped.items()
        }

        try:
            SalesRecordQueryLog.objects.create(
                user=request.user,
                query_type='SPECIAL_ITEMS_LEGACY',
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                filters_applied={
                    'start_md': start_md,
                    'end_md': end_md,
                },
                records_returned=len(results)
            )
        except Exception as e:
            print(f"Error creando log: {e}")

        return Response(
            {
                'count': len(results),
                'results': results,
            },
            status=status.HTTP_200_OK,
        )


class SpecialItemsLegacyDownloadView(APIView):
    """
    Endpoint para descargar en Excel todos los ítems especiales legacy filtrados por mes/día.
    Devuelve registros de TODOS los años en el rango para permitir comparativas.

    Query params:
    - start_md: Mes y día inicial en formato MM-DD (requerido), ej: 01-15
    - end_md:   Mes y día final   en formato MM-DD (requerido), ej: 03-09
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # --- Validar parámetros de mes/día ---
        start_md = request.query_params.get('start_md')
        end_md = request.query_params.get('end_md')

        if not start_md or not end_md:
            return Response(
                {'error': 'Se requieren parámetros: start_md y end_md en formato MM-DD (ej: 01-15)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start_month, start_day = int(start_md.split('-')[0]), int(start_md.split('-')[1])
            end_month, end_day = int(end_md.split('-')[0]), int(end_md.split('-')[1])
            if not (1 <= start_month <= 12 and 1 <= start_day <= 31):
                raise ValueError
            if not (1 <= end_month <= 12 and 1 <= end_day <= 31):
                raise ValueError
        except (ValueError, IndexError, AttributeError):
            return Response(
                {'error': 'Formato inválido. Use MM-DD (ej: 01-15)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if (start_month, start_day) > (end_month, end_day):
            return Response(
                {'error': 'El inicio (start_md) no puede ser mayor que el fin (end_md)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # --- Filtrar por mes/día ignorando el año ---
        q_after_start = (
            Q(fecha__month=start_month, fecha__day__gte=start_day) |
            Q(fecha__month__gt=start_month)
        )
        q_before_end = (
            Q(fecha__month=end_month, fecha__day__lte=end_day) |
            Q(fecha__month__lt=end_month)
        )
        qs = SpecialItemsLegacy.objects.filter(
            q_after_start & q_before_end,
            is_active=True,
        ).order_by('fecha', 'nombre')

        rows = list(qs.values('fecha', 'nombre', 'hectolitros', 'cajas'))

        if not rows:
            return Response(
                {'message': 'No hay datos para el rango de fechas seleccionado'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # --- Construir DataFrame y exportar ---
        df = pd.DataFrame(rows)
        df.rename(columns={
            'fecha': 'Fecha',
            'nombre': 'Nombre',
            'hectolitros': 'Hectolitros',
            'cajas': 'Cajas',
        }, inplace=True)

        df['Fecha'] = pd.to_datetime(df['Fecha']).dt.strftime('%Y-%m-%d')
        df['Hectolitros'] = df['Hectolitros'].astype(float)
        df['Cajas'] = df['Cajas'].astype(float)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Legacy')

        output.seek(0)
        filename = f"special_items_legacy_{start_md}_to_{end_md}.xlsx"
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
