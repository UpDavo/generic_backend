from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import datetime
from tada.services.report_service import ReportService
from tada.models import TrafficEvent, ExecutionLog
from tada.utils.constants import APPS, OPERATING_HOURS, DAY_NAMES
from tada.services.command_service import execute_fetch_simple


class DatetimeVariationReportView(APIView):
    """Vista para obtener variación de tráfico por hora durante un rango de semanas"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Obtener parámetros de la query (sin start_hour y end_hour)
            dia = request.query_params.get('dia')
            start_week = request.query_params.get('start_week')
            end_week = request.query_params.get('end_week')
            year = request.query_params.get('year')

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
    """Vista para enviar reportes por email"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            # Obtener parámetros de la query (sin start_hour y end_hour)
            dia = request.query_params.get('dia')
            start_week = request.query_params.get('start_week')
            end_week = request.query_params.get('end_week')
            year = request.query_params.get('year')

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
            report_service.send_report_by_email(
                dia_seleccionado=dia,
                start_week=start_week,
                end_week=end_week,
                year=year,
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
