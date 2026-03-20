from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import datetime, timedelta, time
from tada.services.report_service import ReportService
from tada.models import TrafficEvent, ExecutionLog, SalesRecordQueryLog
from tada.utils.constants import APPS, OPERATING_HOURS, DAY_NAMES
from tada.services.command_service import execute_fetch_simple
from tada.services.braze_service import BrazeService


class DatetimeVariationReportView(APIView):
    """
    Vista para obtener variación de tráfico por hora durante un rango de semanas.
    
    Parámetros de query:
    - dia (requerido): Día de la semana (1=Lunes, 7=Domingo)
    - start_week (opcional): Semana de inicio (ISO). Si no se proporciona, se calculan automáticamente 4 semanas atrás
    - end_week (opcional): Semana de fin (ISO). Si no se proporciona, usa la semana actual
    - start_year (opcional): Año ISO para start_week
    - end_year (opcional): Año ISO para end_week
    - year (opcional, deprecated): Año ISO para end_week. Use end_year en su lugar
    
    Ejemplos:
    - /tada/reports/datetime-variation/?dia=1  (últimas 4 semanas del día lunes)
    - /tada/reports/datetime-variation/?dia=1&start_week=52&start_year=2025&end_week=1&end_year=2026  (explícito para cruce de años)
    - /tada/reports/datetime-variation/?dia=1&end_week=1&end_year=2026  (automáticamente calcula start_week/start_year)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Obtener parámetros de la query (sin start_hour y end_hour)
            dia = request.query_params.get('dia')
            start_week = request.query_params.get('start_week')
            end_week = request.query_params.get('end_week')
            year = request.query_params.get('year')  # Deprecated
            start_year = request.query_params.get('start_year')
            end_year = request.query_params.get('end_year')

            # Validar parámetro obligatorio
            if not dia:
                return Response(
                    {'error': 'El parámetro "dia" es obligatorio'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir parámetros a int
            try:
                dia = int(dia)
                if dia < 1 or dia > 7:
                    raise ValueError("El día debe estar entre 1 y 7")
            except ValueError:
                return Response(
                    {'error': 'El parámetro "dia" debe ser un entero entre 1 (Lunes) y 7 (Domingo)'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir parámetros opcionales
            try:
                if start_week:
                    start_week = int(start_week)
                if end_week:
                    end_week = int(end_week)
                if year:
                    year = int(year)
                if start_year:
                    start_year = int(start_year)
                if end_year:
                    end_year = int(end_year)
            except ValueError:
                return Response(
                    {'error': 'Los parámetros numéricos deben ser enteros válidos'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Obtener horarios desde constantes según el día
            start_hour = None
            end_hour = None
            if dia in OPERATING_HOURS:
                schedule = OPERATING_HOURS[dia]
                start_hour = schedule['start_hour']
                end_hour = schedule['end_hour']
            else:
                return Response(
                    {'error': f'No hay horarios configurados para el día {dia}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Instanciar el servicio de reportes
            report_service = ReportService()

            # Obtener los datos usando horarios de las constantes
            report_data = report_service.get_datetime_variation(
                dia=dia,
                start_week=start_week,
                end_week=end_week,
                year=year,
                start_year=start_year,
                end_year=end_year,
                start_hour=start_hour,
                end_hour=end_hour
            )

            try:
                event = TrafficEvent.objects.get(id=2)
                current_date = datetime.now().date()
                current_time = datetime.now().time()

                ExecutionLog.objects.create(
                    event=event,
                    execution_type='manual',
                    command='Obtencion manual de reporte',
                    date=current_date,
                    time=current_time,
                    app=APPS['EXECUTION']
                )
            except TrafficEvent.DoesNotExist:
                # Si no existe el evento con ID 2, crear log de error pero continuar
                print(
                    "Warning: TrafficEvent con ID 2 no encontrado. No se registró en ExecutionLog.")
            except Exception as log_error:
                # Si hay error al crear el log, no fallar la operación principal
                print(f"Error al crear ExecutionLog: {log_error}")

            # Preparar respuesta con metadatos adicionales
            response_data = {
                'success': True,
                'data': report_data,
                'metadata': {
                    'dia': dia,
                    'dia_nombre': DAY_NAMES.get(dia, "Desconocido"),
                    'start_week': start_week,
                    'end_week': end_week,
                    'year': year or datetime.now().year,
                    'start_hour': start_hour,
                    'end_hour': end_hour,
                    'horario_range': f"{start_hour:02d}:00-{end_hour:02d}:00",
                    'crosses_midnight': start_hour > end_hour,
                    'schedule_source': 'OPERATING_HOURS',
                    'generated_at': datetime.now().isoformat()
                }
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Error interno del servidor: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReportFetchView(APIView):
    """Vista para obtener reportes"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            execute_fetch_simple()

            # Preparar respuesta
            response_data = {
                'success': True,
                'message': f'Data tomada correctamente para la hora actual',
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Error interno del servidor: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReportEmailView(APIView):
    """
    Vista para enviar reportes por email/WhatsApp.
    
    Parámetros de query:
    - dia (requerido): Día de la semana (1=Lunes, 7=Domingo)
    - start_week (opcional): Semana de inicio (ISO). Si no se proporciona, se calculan automáticamente 4 semanas atrás
    - end_week (opcional): Semana de fin (ISO). Si no se proporciona, usa la semana actual
    - start_year (opcional): Año ISO para start_week
    - end_year (opcional): Año ISO para end_week
    - year (opcional, deprecated): Año ISO para end_week. Use end_year en su lugar
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Obtener parámetros de la query (sin start_hour y end_hour)
            dia = request.query_params.get('dia')
            start_week = request.query_params.get('start_week')
            end_week = request.query_params.get('end_week')
            year = request.query_params.get('year')  # Deprecated
            start_year = request.query_params.get('start_year')
            end_year = request.query_params.get('end_year')

            # Validar parámetro obligatorio
            if not dia:
                return Response(
                    {'error': 'El parámetro "dia" es obligatorio'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir parámetros a int
            try:
                dia = int(dia)
                if dia < 1 or dia > 7:
                    raise ValueError("El día debe estar entre 1 y 7")
            except ValueError:
                return Response(
                    {'error': 'El parámetro "dia" debe ser un entero entre 1 (Lunes) y 7 (Domingo)'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Convertir parámetros opcionales
            try:
                if start_week:
                    start_week = int(start_week)
                if end_week:
                    end_week = int(end_week)
                if year:
                    year = int(year)
                if start_year:
                    start_year = int(start_year)
                if end_year:
                    end_year = int(end_year)
            except ValueError:
                return Response(
                    {'error': 'Los parámetros numéricos deben ser enteros válidos'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Obtener horarios desde constantes según el día
            start_hour = None
            end_hour = None
            if dia in OPERATING_HOURS:
                schedule = OPERATING_HOURS[dia]
                start_hour = schedule['start_hour']
                end_hour = schedule['end_hour']
            else:
                return Response(
                    {'error': f'No hay horarios configurados para el día {dia}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Instanciar el servicio de reportes
            report_service = ReportService()

            # Enviar el reporte con todos los parámetros
            # report_service.send_report_by_email(
            #     dia_seleccionado=dia,
            #     start_week=start_week,
            #     end_week=end_week,
            #     year=year,
            #     start_year=start_year,
            #     end_year=end_year,
            #     start_hour=start_hour,
            #     end_hour=end_hour
            # )

            # Enviar el reporte por WhatsApp
            report_service.send_report_by_whatsapp(
                dia_seleccionado=dia,
                start_week=start_week,
                end_week=end_week,
                year=year,
                start_year=start_year,
                end_year=end_year,
                start_hour=start_hour,
                end_hour=end_hour
            )

            # Registrar la ejecución en ExecutionLog
            current_date = datetime.now().date()
            current_time = datetime.now().time()

            try:
                event = TrafficEvent.objects.get(id=2)

                # Crear descripción del comando con todos los parámetros
                command_description = f"Envío de Reporte por Email - Día: {DAY_NAMES.get(dia, 'Desconocido')}"
                if start_week:
                    command_description += f", Semana inicio: {start_week}"
                if end_week:
                    command_description += f", Semana fin: {end_week}"
                if year:
                    command_description += f", Año: {year}"
                command_description += f", Rango horario: {start_hour:02d}:00 - {end_hour:02d}:00"

                ExecutionLog.objects.create(
                    event=event,
                    execution_type='automatic',
                    command=command_description,
                    date=current_date,
                    time=current_time,
                    app=APPS['EXECUTION']
                )
            except TrafficEvent.DoesNotExist:
                # Si no existe el evento con ID 2, crear log de error pero continuar
                print(
                    "Warning: TrafficEvent con ID 2 no encontrado. No se registró en ExecutionLog.")
            except Exception as log_error:
                # Si hay error al crear el log, no fallar la operación principal
                print(f"Error al crear ExecutionLog: {log_error}")

            # Preparar respuesta
            response_data = {
                'success': True,
                'message': f'Reporte enviado por email exitosamente para el día {DAY_NAMES.get(dia, "Desconocido")}',
                'parameters': {
                    'dia': dia,
                    'dia_nombre': DAY_NAMES.get(dia, "Desconocido"),
                    'start_week': start_week,
                    'end_week': end_week,
                    'year': year or datetime.now().year,
                    'start_hour': start_hour,
                    'end_hour': end_hour,
                    'horario_range': f"{start_hour:02d}:00-{end_hour:02d}:00",
                    'crosses_midnight': start_hour > end_hour,
                    'schedule_source': 'OPERATING_HOURS'
                },
                'sent_at': datetime.now().isoformat(),
                'execution_logged': True
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'error': f'Error interno del servidor: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class SalesByDateRangeView(APIView):
    """
    Retorna ventas por hora agrupadas por día dado un rango de fechas.

    Parámetros de query:
    - start_date (requerido): Fecha de inicio en formato YYYY-MM-DD
    - end_date (requerido): Fecha de fin en formato YYYY-MM-DD

    Ejemplo:
    - /tada/reports/sales-by-date-range/?start_date=2026-03-11&end_date=2026-03-18
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        start_date_str = request.query_params.get('start_date')
        end_date_str = request.query_params.get('end_date')

        if not start_date_str or not end_date_str:
            return Response(
                {'error': 'Los parámetros "start_date" y "end_date" son obligatorios'},
                status=status.HTTP_400_BAD_REQUEST
            )

        start_date = parse_date(start_date_str)
        end_date = parse_date(end_date_str)

        if start_date is None:
            return Response(
                {'error': 'El formato de "start_date" es inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if end_date is None:
            return Response(
                {'error': 'El formato de "end_date" es inválido. Use YYYY-MM-DD'},
                status=status.HTTP_400_BAD_REQUEST
            )
        if start_date > end_date:
            return Response(
                {'error': '"start_date" no puede ser posterior a "end_date"'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            ending_at = min(
                datetime.combine(end_date, time(23, 59, 59)),
                datetime.now().replace(microsecond=0)
            )
            start_dt = datetime.combine(start_date, time(0, 0, 0))

            event = TrafficEvent.objects.get(id=2)
            braze = BrazeService()

            # Braze limita length a 100 por llamada — paginar hacia atrás
            all_entries = []
            current_ending_at = ending_at
            while current_ending_at > start_dt:
                chunk_length = min(100, int((current_ending_at - start_dt).total_seconds() / 3600) + 1)
                data, _ = braze.get_data_series(
                    event_id=event.braze_id,
                    length=chunk_length,
                    ending_at=current_ending_at,
                    unit='hour'
                )
                all_entries.extend(data.get('data', []))
                current_ending_at -= timedelta(hours=100)

            days_map = {}
            for entry in all_entries:
                ts = datetime.fromisoformat(entry['time']).replace(tzinfo=None)
                date_part = ts.date()
                if date_part < start_date or date_part > end_date:
                    continue
                count = entry.get('count', 0)
                if count <= 0:
                    continue
                if date_part not in days_map:
                    days_map[date_part] = []
                days_map[date_part].append({'hora': ts.hour, 'ventas': count})

            result = []
            for date_part in sorted(days_map.keys()):
                horas = sorted(days_map[date_part], key=lambda x: x['hora'])
                result.append({
                    'fecha': date_part.isoformat(),
                    'dia': DAY_NAMES[date_part.isoweekday()],
                    'numero': date_part.day,
                    'ventas': horas,
                })

            try:
                SalesRecordQueryLog.objects.create(
                    query_type='list',
                    records_returned=len(result),
                    filters_applied={
                        'start_date': start_date_str,
                        'end_date': end_date_str,
                        'report_type': 'sales_by_date_range'
                    },
                    date=datetime.now().date(),
                    time=datetime.now().time(),
                    app=str(APPS['SALES_CHECK']),
                    user=request.user
                )
            except Exception as log_error:
                print(f"No se pudo crear log de consulta: {log_error}")

            return Response(result, status=status.HTTP_200_OK)

        except TrafficEvent.DoesNotExist:
            return Response(
                {'error': 'No se encontró el evento de tráfico configurado'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except Exception as e:
            import traceback
            print(f"ERROR sales-by-date-range: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': f'Error al obtener datos de Braze: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
