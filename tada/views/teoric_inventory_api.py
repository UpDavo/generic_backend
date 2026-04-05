"""
Vista para procesar inventario teórico por POC y generar reporte de cobertura de garantía.

Endpoint: POST /teoric-inventory/process/
Parámetros:
  - file (multipart): Excel con 3 hojas (Inventario PT, Inventario EN, Pedido)
  - year (int, opcional): año del período de ventas (default: año actual)
  - month (int, opcional): mes del período de ventas (default: mes actual)

Respuesta: archivo Excel descargable con 2 hojas:
  - Resumen por POC: cobertura, LIMITE GARANTÍA, Cobertura %
  - Días de Inventario: días por POC + SKU
"""

import gc
import time
import traceback
from datetime import datetime
from decimal import Decimal

from django.http import HttpResponse
from django.utils.timezone import now
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from tada.models.salesReportLog import SalesReportLog
from tada.services.teoric_inventory_service import TeoricInventoryService
from tada.utils.constants import APPS


class TeoricInventoryProcessorView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Validar presencia y formato del archivo
        if 'file' not in request.FILES:
            return Response(
                {'error': 'Se requiere un archivo Excel en el campo "file"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'El archivo debe ser un Excel (.xlsx o .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Parsear year y month (default: período actual)
        current_dt = datetime.now()
        try:
            year = int(request.data.get('year', current_dt.year))
            month = int(request.data.get('month', current_dt.month))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Los parámetros year y month deben ser enteros válidos'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not (1 <= month <= 12):
            return Response(
                {'error': 'El parámetro month debe estar entre 1 y 12'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            excel_file.seek(0)
            file_content = excel_file.read()

            start_time = time.time()

            service = TeoricInventoryService()
            output, total_rows = service.process(file_content, year, month)

            end_time = time.time()
            processing_duration = Decimal(str(round(end_time - start_time, 3)))

            # Crear log del procesamiento
            SalesReportLog.objects.create(
                filename=excel_file.name,
                rows_processed=total_rows,
                date=now().date(),
                time=now().time(),
                processing_time_seconds=processing_duration,
                app=str(APPS['SALES']),
                user=request.user
            )

            timestamp = current_dt.strftime('%Y%m%d_%H%M%S')
            filename = f'inventario_teorico_{year}_{str(month).zfill(2)}_{timestamp}.xlsx'

            response = HttpResponse(
                output.read(),
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = f'attachment; filename="{filename}"'

            del file_content, output
            gc.collect()

            return response

        except ValueError as exc:
            return Response(
                {'error': str(exc)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:
            traceback.print_exc()
            return Response(
                {'error': f'Error al procesar el archivo: {str(exc)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
