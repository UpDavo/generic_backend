from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.http import HttpResponse
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta, date
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
import pandas as pd
from io import BytesIO
from collections import defaultdict
from decimal import Decimal, InvalidOperation

from tada.models import HectolitresDailyMeta, SalesRecord, SalesRecordQueryLog
from tada.utils.constants import APPS
from tada.serializers import (
    HectolitresDailyMetaSerializer,
    HectolitresDailyMetaCreateSerializer,
    HectolitresDailyMetaUpdateSerializer,
    HectolitresDailyMetaListSerializer
)


class HectolitresDailyMetaListCreateView(APIView):
    """
    Vista para listar todas las metas diarias de hectolitros o crear una nueva.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Listar todas las metas diarias de hectolitros con filtros opcionales.
        """
        queryset = HectolitresDailyMeta.objects.all()

        # Filtrar por fecha específica
        date_param = request.query_params.get('date')
        if date_param:
            try:
                date_obj = parse_date(date_param)
                if date_obj:
                    queryset = queryset.filter(date=date_obj)
            except ValueError:
                pass

        # Filtrar por rango de fechas
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        if start_date:
            try:
                start_date_obj = parse_date(start_date)
                if start_date_obj:
                    queryset = queryset.filter(date__gte=start_date_obj)
            except ValueError:
                pass

        if end_date:
            try:
                end_date_obj = parse_date(end_date)
                if end_date_obj:
                    queryset = queryset.filter(date__lte=end_date_obj)
            except ValueError:
                pass

        queryset = queryset.order_by('-date')
        serializer = HectolitresDailyMetaListSerializer(queryset, many=True)
        return Response(serializer.data)

    def post(self, request):
        """
        Crear una nueva meta diaria de hectolitros.
        """
        serializer = HectolitresDailyMetaCreateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class HectolitresDailyMetaRetrieveUpdateDestroyView(APIView):
    """
    Vista para obtener, actualizar o eliminar una meta diaria de hectolitros específica.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, pk):
        return get_object_or_404(HectolitresDailyMeta, pk=pk)

    def get(self, request, pk):
        """
        Obtener una meta diaria de hectolitros específica.
        """
        meta = self.get_object(pk)
        serializer = HectolitresDailyMetaSerializer(meta)
        return Response(serializer.data)

    def put(self, request, pk):
        """
        Actualizar completamente una meta diaria de hectolitros.
        """
        meta = self.get_object(pk)
        serializer = HectolitresDailyMetaUpdateSerializer(
            meta, data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def patch(self, request, pk):
        """
        Actualizar parcialmente una meta diaria de hectolitros.
        """
        meta = self.get_object(pk)
        serializer = HectolitresDailyMetaUpdateSerializer(
            meta, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, pk):
        """
        Eliminar una meta diaria de hectolitros.
        """
        meta = self.get_object(pk)
        meta.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class HectolitresDailyMetaBulkCreateView(APIView):
    """
    Vista para crear múltiples metas de hectolitros de una vez.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Crear múltiples metas de hectolitros de una vez.

        Body esperado:
        {
            "metas": [
                {
                    "date": "2023-12-25",
                    "target_hectolitres": 150.50
                },
                ...
            ]
        }
        """
        metas_data = request.data.get('metas', [])

        if not metas_data or not isinstance(metas_data, list):
            return Response(
                {'error': 'Se requiere una lista de metas en el campo "metas"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_metas = []
        errors = []

        for i, meta_data in enumerate(metas_data):
            serializer = HectolitresDailyMetaCreateSerializer(data=meta_data)
            if serializer.is_valid():
                try:
                    meta = serializer.save()
                    created_metas.append(
                        HectolitresDailyMetaSerializer(meta).data)
                except Exception as e:
                    errors.append(f"Item {i}: {str(e)}")
            else:
                errors.append(f"Item {i}: {serializer.errors}")

        response_data = {
            'created': len(created_metas),
            'errors': len(errors),
            'results': created_metas
        }

        if errors:
            response_data['error_details'] = errors

        return Response(
            response_data,
            status=status.HTTP_201_CREATED if created_metas else status.HTTP_400_BAD_REQUEST
        )


class HectolitresDailyMetaBulkCreateFromExcelView(APIView):
    """
    Vista para crear múltiples metas diarias de hectolitros desde un archivo Excel.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Crear o actualizar múltiples metas de hectolitros desde un archivo Excel.

        El archivo Excel debe tener las columnas:
        - date: Fecha en formato YYYY-MM-DD
        - goal: Meta de hectolitros para el día (decimal)

        Comportamiento:
        - Si la fecha no existe: crea una nueva meta
        - Si la fecha ya existe: actualiza la meta existente
        """
        if 'file' not in request.FILES:
            return Response(
                {'error': 'Se requiere un archivo Excel en el campo "file"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        excel_file = request.FILES['file']

        # Validar que sea un archivo Excel
        if not excel_file.name.endswith(('.xlsx', '.xls')):
            return Response(
                {'error': 'El archivo debe ser un Excel (.xlsx o .xls)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Leer el archivo Excel
            df = pd.read_excel(BytesIO(excel_file.read()))

            # Validar que las columnas requeridas existan
            required_columns = ['date', 'goal']
            missing_columns = [
                col for col in required_columns if col not in df.columns]

            if missing_columns:
                return Response(
                    {'error': f'Columnas faltantes en el archivo: {", ".join(missing_columns)}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            created_metas = []
            errors = []

            # Procesar cada fila del Excel
            for index, row in df.iterrows():
                try:
                    # Validar y convertir la fecha
                    date_value = row['date']
                    if pd.isna(date_value):
                        # +2 por encabezado y índice 0
                        errors.append(f"Fila {index+2}: Fecha vacía")
                        continue

                    # Si es un timestamp de pandas, convertir a fecha
                    if isinstance(date_value, pd.Timestamp):
                        date_str = date_value.strftime('%Y-%m-%d')
                    else:
                        date_str = str(date_value)

                    # Validar y convertir la meta de hectolitros
                    goal_value = row['goal']
                    if pd.isna(goal_value):
                        errors.append(
                            f"Fila {index+2}: Meta de hectolitros vacía")
                        continue

                    try:
                        # Usar Decimal para mantener precisión de 3 decimales
                        target_hectolitres = Decimal(str(goal_value)).quantize(Decimal('0.001'))
                    except (ValueError, TypeError, InvalidOperation):
                        errors.append(
                            f"Fila {index+2}: Meta debe ser un número válido")
                        continue

                    # Crear o actualizar el objeto meta
                    meta_data = {
                        'date': date_str,
                        'target_hectolitres': target_hectolitres
                    }

                    # Verificar si ya existe una meta para esta fecha
                    existing_meta = HectolitresDailyMeta.objects.filter(
                        date=date_str).first()

                    if existing_meta:
                        # Actualizar meta existente
                        serializer = HectolitresDailyMetaUpdateSerializer(
                            existing_meta, data=meta_data, partial=True)
                        if serializer.is_valid():
                            try:
                                meta = serializer.save()
                                created_metas.append({
                                    'date': meta.date,
                                    'target_hectolitres': str(meta.target_hectolitres),
                                    'id': meta.id,
                                    'action': 'updated'
                                })
                            except Exception as e:
                                errors.append(
                                    f"Fila {index+2}: Error al actualizar - {str(e)}")
                        else:
                            errors.append(
                                f"Fila {index+2}: Error de validación al actualizar - {serializer.errors}")
                    else:
                        # Crear nueva meta
                        serializer = HectolitresDailyMetaCreateSerializer(
                            data=meta_data)
                        if serializer.is_valid():
                            try:
                                meta = serializer.save()
                                created_metas.append({
                                    'date': meta.date,
                                    'target_hectolitres': str(meta.target_hectolitres),
                                    'id': meta.id,
                                    'action': 'created'
                                })
                            except Exception as e:
                                errors.append(
                                    f"Fila {index+2}: Error al crear - {str(e)}")
                        else:
                            errors.append(
                                f"Fila {index+2}: Error de validación al crear - {serializer.errors}")

                except Exception as e:
                    errors.append(
                        f"Fila {index+2}: Error inesperado - {str(e)}")

            # Contar las acciones realizadas
            created_count = len(
                [m for m in created_metas if m.get('action') == 'created'])
            updated_count = len(
                [m for m in created_metas if m.get('action') == 'updated'])

            response_data = {
                'total_processed': len(created_metas),
                'created': created_count,
                'updated': updated_count,
                'total_rows': len(df),
                'errors_count': len(errors),
                'results': created_metas
            }

            if errors:
                response_data['errors'] = errors

            # Si se procesaron algunas metas, devolver 201, sino 400
            status_code = status.HTTP_201_CREATED if created_metas else status.HTTP_400_BAD_REQUEST

            return Response(response_data, status=status_code)

        except Exception as e:
            return Response(
                {'error': f'Error al procesar el archivo Excel: {str(e)}'},
                status=status.HTTP_400_BAD_REQUEST
            )


class HectolitresWeeklyReportView(APIView):
    """
    Vista para obtener reporte de hectolitros por semana con metas y cumplimiento.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener reporte de hectolitros filtrado por año y semana.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)

        Returns:
        {
            "total": {
                "ht_vendidos": float,
                "ht_meta": float,
                "cumplimiento": "XX.XX%"
            },
            "w1": {
                "lun": {
                    "dia": 1,
                    "ht": float,
                    "ht_meta": float,
                    "cumplimiento": "XX.XX%"
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
                {'error': 'Se requieren parámetros válidos: start_year, end_year, start_week, end_week'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar rangos
        if start_week < 1 or start_week > 53 or end_week < 1 or end_week > 53:
            return Response(
                {'error': 'Las semanas deben estar entre 1 y 53'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'El año inicial no puede ser mayor que el año final'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generar lista de fechas para el rango de semanas
        date_ranges = self._generate_date_ranges(
            start_year, end_year, start_week, end_week)

        if not date_ranges:
            return Response(
                {'error': 'No se pudieron generar fechas válidas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener ventas agrupadas por fecha (sumar hectolitros)
        sales_by_date = self._get_sales_by_date(
            date_ranges['start_date'], date_ranges['end_date'])

        # Obtener metas por fecha
        metas_by_date = self._get_metas_by_date(
            date_ranges['start_date'], date_ranges['end_date'])

        # Construir respuesta estructurada por semanas
        response_data = self._build_weekly_response(
            date_ranges['weeks_data'],
            sales_by_date,
            metas_by_date
        )

        # Crear log de la consulta con tipo SALES_CHECK
        try:
            # Calcular cantidad de registros consultados (días * ventas por día)
            total_records = sum(len(week['dates']) for week in date_ranges['weeks_data'])
            
            SalesRecordQueryLog.objects.create(
                query_type='list',
                records_returned=total_records,
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'report_type': 'hectolitres_weekly'
                },
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                user=request.user
            )
        except Exception as e:
            # No fallar la consulta si no se puede crear el log
            print(f"⚠️ No se pudo crear log de consulta: {str(e)}")

        return Response(response_data, status=status.HTTP_200_OK)

    def _generate_date_ranges(self, start_year, end_year, start_week, end_week):
        """
        Generar las fechas para el rango de semanas especificado.

        Returns:
            dict con 'start_date', 'end_date' y 'weeks_data' (lista de semanas con sus fechas)
        """
        weeks_data = []

        # Caso simple: mismo año
        if start_year == end_year:
            for week_num in range(start_week, end_week + 1):
                week_dates = self._get_week_dates(start_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': start_year,
                        'week': week_num,
                        'dates': week_dates
                    })
        else:
            # Múltiples años
            # Año inicial: desde start_week hasta semana 52/53
            last_week_start_year = date(start_year, 12, 28).isocalendar()[1]
            for week_num in range(start_week, last_week_start_year + 1):
                week_dates = self._get_week_dates(start_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': start_year,
                        'week': week_num,
                        'dates': week_dates
                    })

            # Años intermedios (si hay)
            for year in range(start_year + 1, end_year):
                last_week_year = date(year, 12, 28).isocalendar()[1]
                for week_num in range(1, last_week_year + 1):
                    week_dates = self._get_week_dates(year, week_num)
                    if week_dates:
                        weeks_data.append({
                            'year': year,
                            'week': week_num,
                            'dates': week_dates
                        })

            # Año final: desde semana 1 hasta end_week
            for week_num in range(1, end_week + 1):
                week_dates = self._get_week_dates(end_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': end_year,
                        'week': week_num,
                        'dates': week_dates
                    })

        if not weeks_data:
            return None

        # Obtener fecha inicial y final global
        all_dates = []
        for week_data in weeks_data:
            all_dates.extend([d['date'] for d in week_data['dates']])

        return {
            'start_date': min(all_dates),
            'end_date': max(all_dates),
            'weeks_data': weeks_data
        }

    def _get_week_dates(self, year, week_num):
        """
        Obtener todas las fechas (lun-dom) de una semana ISO específica.

        Returns:
            Lista de dicts con 'date', 'day_name', 'day_number'
        """
        try:
            # Obtener el lunes de la semana ISO
            # ISO week date: el 4 de enero siempre está en la semana 1
            jan_4 = date(year, 1, 4)
            week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
            target_monday = week_1_monday + timedelta(weeks=week_num - 1)

            week_dates = []
            day_names = ['lun', 'mar', 'mie', 'jue', 'vie', 'sab', 'dom']

            for i in range(7):
                current_date = target_monday + timedelta(days=i)
                week_dates.append({
                    'date': current_date,
                    'day_name': day_names[i],
                    'day_number': current_date.day
                })

            return week_dates
        except (ValueError, OverflowError):
            return None

    def _get_sales_by_date(self, start_date, end_date):
        """
        Obtener ventas (hectolitros) agrupadas por fecha.

        Returns:
            dict: {date: Decimal(hectolitros)}
        """
        sales_data = SalesRecord.objects.filter(
            deleted_at__isnull=True,
            date__gte=start_date,
            date__lte=end_date,
            hectolitros__isnull=False
        ).values('date').annotate(
            total_ht=Sum('hectolitros')
        )

        # Convertir a diccionario
        sales_by_date = {}
        for item in sales_data:
            sales_by_date[item['date']] = item['total_ht'] or Decimal('0')

        return sales_by_date

    def _get_metas_by_date(self, start_date, end_date):
        """
        Obtener metas de hectolitros por fecha.

        Returns:
            dict: {date: Decimal(target_hectolitres)}
        """
        metas_data = HectolitresDailyMeta.objects.filter(
            deleted_at__isnull=True,
            date__gte=start_date,
            date__lte=end_date
        ).values('date', 'target_hectolitres')

        # Convertir a diccionario
        metas_by_date = {}
        for item in metas_data:
            metas_by_date[item['date']
                          ] = item['target_hectolitres'] or Decimal('0')

        return metas_by_date

    def _build_weekly_response(self, weeks_data, sales_by_date, metas_by_date):
        """
        Construir la respuesta JSON estructurada por semanas.
        """
        response = {}

        # Totales globales
        total_ht_vendidos = Decimal('0')
        total_ht_meta = Decimal('0')

        # Procesar cada semana
        for week_data in weeks_data:
            week_key = f"w{week_data['week']}"
            week_response = {}

            # Procesar cada día de la semana
            for day_data in week_data['dates']:
                current_date = day_data['date']
                day_name = day_data['day_name']

                # Obtener hectolitros vendidos y meta
                ht_vendidos = sales_by_date.get(current_date, Decimal('0'))
                ht_meta = metas_by_date.get(current_date, Decimal('0'))

                # Calcular cumplimiento
                if ht_meta > 0:
                    cumplimiento_pct = (ht_vendidos / ht_meta) * 100
                    cumplimiento_str = f"{cumplimiento_pct:.2f}%"
                else:
                    cumplimiento_str = "N/A"

                # Agregar al total
                total_ht_vendidos += ht_vendidos
                total_ht_meta += ht_meta

                # Construir objeto del día
                week_response[day_name] = {
                    'dia': day_data['day_number'],
                    'fecha': current_date.strftime('%Y-%m-%d'),
                    'ht': round(float(ht_vendidos), 3),
                    'ht_meta': round(float(ht_meta), 3),
                    'cumplimiento': cumplimiento_str
                }

            response[week_key] = week_response

        # Calcular cumplimiento total
        if total_ht_meta > 0:
            cumplimiento_total_pct = (total_ht_vendidos / total_ht_meta) * 100
            cumplimiento_total_str = f"{cumplimiento_total_pct:.2f}%"
        else:
            cumplimiento_total_str = "N/A"

        # Agregar totales al inicio
        response = {
            'total': {
                'ht_vendidos': round(float(total_ht_vendidos), 3),
                'ht_meta': round(float(total_ht_meta), 3),
                'cumplimiento': cumplimiento_total_str
            },
            **response
        }

        return response


class HectolitresWeeklyReportDownloadView(APIView):
    """
    Vista para descargar el reporte de hectolitros por semana en Excel.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar reporte de hectolitros en Excel filtrado por año y semana.

        Query params:
        - start_year: Año inicial (requerido)
        - end_year: Año final (requerido)
        - start_week: Semana inicial (requerido, 1-53)
        - end_week: Semana final (requerido, 1-53)

        Returns:
        Archivo Excel con el reporte estructurado por semanas
        """
        # Validar parámetros requeridos
        try:
            start_year = int(request.query_params.get('start_year'))
            end_year = int(request.query_params.get('end_year'))
            start_week = int(request.query_params.get('start_week'))
            end_week = int(request.query_params.get('end_week'))
        except (TypeError, ValueError):
            return Response(
                {'error': 'Se requieren parámetros válidos: start_year, end_year, start_week, end_week'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Validar rangos
        if start_week < 1 or start_week > 53 or end_week < 1 or end_week > 53:
            return Response(
                {'error': 'Las semanas deben estar entre 1 y 53'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if start_year > end_year:
            return Response(
                {'error': 'El año inicial no puede ser mayor que el año final'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generar lista de fechas para el rango de semanas
        date_ranges = self._generate_date_ranges(
            start_year, end_year, start_week, end_week)

        if not date_ranges:
            return Response(
                {'error': 'No se pudieron generar fechas válidas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener ventas agrupadas por fecha (sumar hectolitros)
        sales_by_date = self._get_sales_by_date(
            date_ranges['start_date'], date_ranges['end_date'])

        # Obtener metas por fecha
        metas_by_date = self._get_metas_by_date(
            date_ranges['start_date'], date_ranges['end_date'])

        # Construir DataFrame para Excel
        df = self._build_excel_dataframe(
            date_ranges['weeks_data'],
            sales_by_date,
            metas_by_date
        )

        # Crear log de la descarga con tipo SALES_CHECK
        try:
            SalesRecordQueryLog.objects.create(
                query_type='download',
                records_returned=len(df),
                filters_applied={
                    'start_year': start_year,
                    'end_year': end_year,
                    'start_week': start_week,
                    'end_week': end_week,
                    'report_type': 'hectolitres_weekly'
                },
                date=datetime.now().date(),
                time=datetime.now().time(),
                app=str(APPS['SALES_CHECK']),
                user=request.user
            )
        except Exception as e:
            # No fallar la descarga si no se puede crear el log
            print(f"⚠️ No se pudo crear log de descarga: {str(e)}")

        # Generar archivo Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Reporte Hectolitros')

            # Obtener worksheet para formato
            worksheet = writer.sheets['Reporte Hectolitros']

            # Auto-ajustar ancho de columnas
            for column in worksheet.columns:
                max_length = 0
                column_letter = column[0].column_letter
                for cell in column:
                    try:
                        if len(str(cell.value)) > max_length:
                            max_length = len(str(cell.value))
                    except:
                        pass
                adjusted_width = min(max_length + 2, 50)
                worksheet.column_dimensions[column_letter].width = adjusted_width

        output.seek(0)

        # Generar nombre de archivo con timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'reporte_hectolitros_semanal_{start_year}W{start_week}_{end_year}W{end_week}_{timestamp}.xlsx'

        # Crear respuesta HTTP con el archivo Excel
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _generate_date_ranges(self, start_year, end_year, start_week, end_week):
        """
        Generar las fechas para el rango de semanas especificado.
        (Mismo método que HectolitresWeeklyReportView)
        """
        weeks_data = []

        # Caso simple: mismo año
        if start_year == end_year:
            for week_num in range(start_week, end_week + 1):
                week_dates = self._get_week_dates(start_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': start_year,
                        'week': week_num,
                        'dates': week_dates
                    })
        else:
            # Múltiples años
            last_week_start_year = date(start_year, 12, 28).isocalendar()[1]
            for week_num in range(start_week, last_week_start_year + 1):
                week_dates = self._get_week_dates(start_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': start_year,
                        'week': week_num,
                        'dates': week_dates
                    })

            for year in range(start_year + 1, end_year):
                last_week_year = date(year, 12, 28).isocalendar()[1]
                for week_num in range(1, last_week_year + 1):
                    week_dates = self._get_week_dates(year, week_num)
                    if week_dates:
                        weeks_data.append({
                            'year': year,
                            'week': week_num,
                            'dates': week_dates
                        })

            for week_num in range(1, end_week + 1):
                week_dates = self._get_week_dates(end_year, week_num)
                if week_dates:
                    weeks_data.append({
                        'year': end_year,
                        'week': week_num,
                        'dates': week_dates
                    })

        if not weeks_data:
            return None

        all_dates = []
        for week_data in weeks_data:
            all_dates.extend([d['date'] for d in week_data['dates']])

        return {
            'start_date': min(all_dates),
            'end_date': max(all_dates),
            'weeks_data': weeks_data
        }

    def _get_week_dates(self, year, week_num):
        """
        Obtener todas las fechas (lun-dom) de una semana ISO específica.
        (Mismo método que HectolitresWeeklyReportView)
        """
        try:
            jan_4 = date(year, 1, 4)
            week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
            target_monday = week_1_monday + timedelta(weeks=week_num - 1)

            week_dates = []
            day_names = ['Lunes', 'Martes', 'Miércoles',
                         'Jueves', 'Viernes', 'Sábado', 'Domingo']

            for i in range(7):
                current_date = target_monday + timedelta(days=i)
                week_dates.append({
                    'date': current_date,
                    'day_name': day_names[i],
                    'day_number': current_date.day
                })

            return week_dates
        except (ValueError, OverflowError):
            return None

    def _get_sales_by_date(self, start_date, end_date):
        """
        Obtener ventas (hectolitros) agrupadas por fecha.
        (Mismo método que HectolitresWeeklyReportView)
        """
        sales_data = SalesRecord.objects.filter(
            deleted_at__isnull=True,
            date__gte=start_date,
            date__lte=end_date,
            hectolitros__isnull=False
        ).values('date').annotate(
            total_ht=Sum('hectolitros')
        )

        sales_by_date = {}
        for item in sales_data:
            sales_by_date[item['date']] = item['total_ht'] or Decimal('0')

        return sales_by_date

    def _get_metas_by_date(self, start_date, end_date):
        """
        Obtener metas de hectolitros por fecha.
        (Mismo método que HectolitresWeeklyReportView)
        """
        metas_data = HectolitresDailyMeta.objects.filter(
            deleted_at__isnull=True,
            date__gte=start_date,
            date__lte=end_date
        ).values('date', 'target_hectolitres')

        metas_by_date = {}
        for item in metas_data:
            metas_by_date[item['date']
                          ] = item['target_hectolitres'] or Decimal('0')

        return metas_by_date

    def _build_excel_dataframe(self, weeks_data, sales_by_date, metas_by_date):
        """
        Construir DataFrame estructurado para Excel.
        """
        rows = []

        # Totales globales
        total_ht_vendidos = Decimal('0')
        total_ht_meta = Decimal('0')

        # Procesar cada semana
        for week_data in weeks_data:
            week_num = week_data['week']
            year = week_data['year']

            # Procesar cada día de la semana
            for day_data in week_data['dates']:
                current_date = day_data['date']
                day_name = day_data['day_name']

                # Obtener hectolitros vendidos y meta
                ht_vendidos = sales_by_date.get(current_date, Decimal('0'))
                ht_meta = metas_by_date.get(current_date, Decimal('0'))

                # Calcular cumplimiento
                if ht_meta > 0:
                    cumplimiento_pct = float((ht_vendidos / ht_meta) * 100)
                else:
                    cumplimiento_pct = None

                # Agregar al total
                total_ht_vendidos += ht_vendidos
                total_ht_meta += ht_meta

                # Agregar fila
                rows.append({
                    'Año': year,
                    'Semana': week_num,
                    'Día Semana': day_name,
                    'Fecha': current_date.strftime('%Y-%m-%d'),
                    'Día': day_data['day_number'],
                    'Hectolitros Vendidos': round(float(ht_vendidos), 3),
                    'Hectolitros Meta': round(float(ht_meta), 3),
                    'Cumplimiento %': cumplimiento_pct
                })

        # Crear DataFrame
        df = pd.DataFrame(rows)

        # Agregar fila de totales al inicio
        if total_ht_meta > 0:
            cumplimiento_total_pct = float(
                (total_ht_vendidos / total_ht_meta) * 100)
        else:
            cumplimiento_total_pct = None

        total_row = pd.DataFrame([{
            'Año': 'TOTAL',
            'Semana': '',
            'Día Semana': '',
            'Fecha': '',
            'Día': '',
            'Hectolitros Vendidos': round(float(total_ht_vendidos), 3),
            'Hectolitros Meta': round(float(total_ht_meta), 3),
            'Cumplimiento %': cumplimiento_total_pct
        }])

        # Concatenar fila de totales + datos
        df = pd.concat([total_row, df], ignore_index=True)

        return df
