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
    Filtra por rango de fechas y agrupa por semanas (mostrando solo días dentro del rango).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtener reporte de hectolitros o cajas filtrado por rango de fechas, agrupado por semanas.

        Query params:
        - start_date: Fecha inicial en formato YYYY-MM-DD (requerido)
        - end_date: Fecha final en formato YYYY-MM-DD (requerido)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)

        Ejemplo: start_date=2026-01-01&end_date=2026-01-31
        Devuelve semanas 1 a 5, pero la semana 5 solo incluye los días hasta el 31.

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
                    "fecha": "2026-01-05",
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
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generar lista de fechas para el rango, agrupadas por semanas
        date_ranges = self._generate_date_ranges_from_dates(start_date_obj, end_date_obj)

        if not date_ranges:
            return Response(
                {'error': 'No se pudieron generar fechas válidas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener ventas agrupadas por fecha (sumar hectolitros o cajas)
        sales_by_date = self._get_sales_by_date(
            start_date_obj, end_date_obj, report_type)

        # Obtener metas por fecha
        metas_by_date = self._get_metas_by_date(start_date_obj, end_date_obj)

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
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': f'hectolitres_weekly_{report_type}'
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

    def _generate_date_ranges_from_dates(self, start_date, end_date):
        """
        Generar las fechas agrupadas por semanas para un rango de fechas.
        Solo incluye los días que están dentro del rango especificado.

        Args:
            start_date: fecha inicial (date object)
            end_date: fecha final (date object)

        Returns:
            dict con 'start_date', 'end_date' y 'weeks_data' (lista de semanas con sus fechas)
        """
        weeks_data = []
        day_names = ['lun', 'mar', 'mie', 'jue', 'vie', 'sab', 'dom']
        
        # Agrupar fechas por semana ISO
        current_date = start_date
        current_week_data = None
        
        while current_date <= end_date:
            iso_calendar = current_date.isocalendar()
            week_num = iso_calendar[1]
            year = iso_calendar[0]  # año ISO (puede diferir del año calendario)
            day_of_week = iso_calendar[2] - 1  # 0=lun, 6=dom
            
            # Si es una nueva semana, crear nuevo registro
            if current_week_data is None or current_week_data['week'] != week_num or current_week_data['year'] != year:
                if current_week_data is not None:
                    weeks_data.append(current_week_data)
                
                current_week_data = {
                    'year': year,
                    'week': week_num,
                    'dates': []
                }
            
            # Agregar el día actual a la semana
            current_week_data['dates'].append({
                'date': current_date,
                'day_name': day_names[day_of_week],
                'day_number': current_date.day
            })
            
            current_date += timedelta(days=1)
        
        # Agregar la última semana
        if current_week_data is not None and current_week_data['dates']:
            weeks_data.append(current_week_data)
        
        if not weeks_data:
            return None

        return {
            'start_date': start_date,
            'end_date': end_date,
            'weeks_data': weeks_data
        }

    def _get_sales_by_date(self, start_date, end_date, report_type='hectolitros'):
        """
        Obtener ventas (hectolitros o cajas) agrupadas por fecha.

        Returns:
            dict: {date: Decimal(hectolitros o cajas)}
        """
        from django.db.models import F, DecimalField, ExpressionWrapper
        
        if report_type == 'hectolitros':
            sales_data = SalesRecord.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                hectolitros__isnull=False
            ).values('date').annotate(
                total_ht=Sum('hectolitros')
            )
        else:  # caja
            sales_data = SalesRecord.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                orders__isnull=False,
                units_assigned__isnull=False,
                unidades_por_caja__isnull=False
            ).values('date').annotate(
                total_ht=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
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
    Filtra por rango de fechas y agrupa por semanas (mostrando solo días dentro del rango).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Descargar reporte de hectolitros o cajas en Excel filtrado por rango de fechas.

        Query params:
        - start_date: Fecha inicial en formato YYYY-MM-DD (requerido)
        - end_date: Fecha final en formato YYYY-MM-DD (requerido)
        - report_type: "hectolitros" o "caja" (opcional, default: hectolitros)

        Ejemplo: start_date=2026-01-01&end_date=2026-01-31
        Devuelve semanas 1 a 5, pero la semana 5 solo incluye los días hasta el 31.

        Returns:
        Archivo Excel con el reporte estructurado por semanas
        """
        # Validar parámetros requeridos
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
        report_type = request.query_params.get('report_type', 'hectolitros').strip().lower()
        if report_type not in ['hectolitros', 'caja']:
            return Response(
                {'error': 'report_type debe ser "hectolitros" o "caja" (opcional, default: hectolitros)'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Generar lista de fechas para el rango, agrupadas por semanas
        date_ranges = self._generate_date_ranges_from_dates(start_date_obj, end_date_obj)

        if not date_ranges:
            return Response(
                {'error': 'No se pudieron generar fechas válidas para el rango especificado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Obtener ventas agrupadas por fecha (sumar hectolitros o cajas)
        sales_by_date = self._get_sales_by_date(
            start_date_obj, end_date_obj, report_type)

        # Obtener metas por fecha
        metas_by_date = self._get_metas_by_date(start_date_obj, end_date_obj)

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
                    'start_date': start_date_str,
                    'end_date': end_date_str,
                    'report_type': f'hectolitres_weekly_{report_type}'
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
        type_label = 'Hectolitros' if report_type == 'hectolitros' else 'Cajas'
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name=f'Reporte {type_label}')

            # Obtener worksheet para formato
            worksheet = writer.sheets[f'Reporte {type_label}']

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
        type_file_label = 'hectolitros' if report_type == 'hectolitros' else 'cajas'
        filename = f'reporte_{type_file_label}_semanal_{start_date_str}_{end_date_str}_{timestamp}.xlsx'

        # Crear respuesta HTTP con el archivo Excel
        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'

        return response

    def _generate_date_ranges_from_dates(self, start_date, end_date):
        """
        Generar las fechas agrupadas por semanas para un rango de fechas.
        Solo incluye los días que están dentro del rango especificado.
        """
        weeks_data = []
        day_names = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']
        
        current_date = start_date
        current_week_data = None
        
        while current_date <= end_date:
            iso_calendar = current_date.isocalendar()
            week_num = iso_calendar[1]
            year = iso_calendar[0]
            day_of_week = iso_calendar[2] - 1  # 0=lun, 6=dom
            
            if current_week_data is None or current_week_data['week'] != week_num or current_week_data['year'] != year:
                if current_week_data is not None:
                    weeks_data.append(current_week_data)
                
                current_week_data = {
                    'year': year,
                    'week': week_num,
                    'dates': []
                }
            
            current_week_data['dates'].append({
                'date': current_date,
                'day_name': day_names[day_of_week],
                'day_number': current_date.day
            })
            
            current_date += timedelta(days=1)
        
        if current_week_data is not None and current_week_data['dates']:
            weeks_data.append(current_week_data)
        
        if not weeks_data:
            return None

        return {
            'start_date': start_date,
            'end_date': end_date,
            'weeks_data': weeks_data
        }

    def _get_sales_by_date(self, start_date, end_date, report_type='hectolitros'):
        """
        Obtener ventas (hectolitros o cajas) agrupadas por fecha.
        (Mismo método que HectolitresWeeklyReportView)
        """
        from django.db.models import F, DecimalField, ExpressionWrapper
        
        if report_type == 'hectolitros':
            sales_data = SalesRecord.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                hectolitros__isnull=False
            ).values('date').annotate(
                total_ht=Sum('hectolitros')
            )
        else:  # caja
            sales_data = SalesRecord.objects.filter(
                deleted_at__isnull=True,
                date__gte=start_date,
                date__lte=end_date,
                orders__isnull=False,
                units_assigned__isnull=False,
                unidades_por_caja__isnull=False
            ).values('date').annotate(
                total_ht=Sum(
                    ExpressionWrapper(
                        (F('orders') * F('units_assigned')) / F('unidades_por_caja'),
                        output_field=DecimalField()
                    )
                )
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
