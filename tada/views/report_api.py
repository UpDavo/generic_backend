from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.utils.dateparse import parse_date
from datetime import datetime
from tada.services.report_service import ReportService
from tada.models import TrafficEvent, ExecutionLog
from tada.utils.constants import APPS


class DatetimeVariationReportView(APIView):
    """Vista para obtener variación de tráfico por hora durante un rango de semanas"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Obtiene la variación de tráfico por hora para un día específico.

        Query Parameters:
        - dia (int, required): Día de la semana (1=Lunes, 2=Martes, ..., 7=Domingo)
        - start_week (int, optional): Número de semana de inicio
        - end_week (int, optional): Número de semana de fin
        - year (int, optional): Año para el cual obtener los datos
        - start_hour (int, optional): Hora de inicio del rango (default: 7)
        - end_hour (int, optional): Hora de fin del rango (default: 3)

        Returns:
        - JSON con datos de variación por hora, variación diaria y comparación con meta
        """
        try:
            # Obtener parámetros de la query
            dia = request.query_params.get('dia')
            start_week = request.query_params.get('start_week')
            end_week = request.query_params.get('end_week')
            year = request.query_params.get('year')
            start_hour = request.query_params.get('start_hour', 7)
            end_hour = request.query_params.get('end_hour', 3)

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
                start_hour = int(start_hour)
                end_hour = int(end_hour)
            except ValueError:
                return Response(
                    {'error': 'Los parámetros numéricos deben ser enteros válidos'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validar rangos de horas
            if start_hour < 0 or start_hour > 23:
                return Response(
                    {'error': 'start_hour debe estar entre 0 y 23'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if end_hour < 0 or end_hour > 23:
                return Response(
                    {'error': 'end_hour debe estar entre 0 y 23'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Instanciar el servicio de reportes
            report_service = ReportService()

            # Obtener los datos
            report_data = report_service.get_datetime_variation(
                dia=dia,
                start_week=start_week,
                end_week=end_week,
                year=year,
                start_hour=start_hour,
                end_hour=end_hour
            )

            # Preparar respuesta con metadatos adicionales
            response_data = {
                'success': True,
                'data': report_data,
                'metadata': {
                    'dia': dia,
                    'dia_nombre': self._get_dia_nombre(dia),
                    'start_week': start_week,
                    'end_week': end_week,
                    'year': year or datetime.now().year,
                    'start_hour': start_hour,
                    'end_hour': end_hour,
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

    def _get_dia_nombre(self, dia):
        """Convierte número de día a nombre"""
        dias_nombres = {
            1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
            5: "Viernes", 6: "Sábado", 7: "Domingo"
        }
        return dias_nombres.get(dia, "Desconocido")


class ReportEmailView(APIView):
    """Vista para enviar reportes por email"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Envía un reporte por email para un día específico.

        Body Parameters:
        - dia (int, required): Día de la semana (1=Lunes, 2=Martes, ..., 7=Domingo)
        - start_week (int, optional): Número de semana de inicio
        - end_week (int, optional): Número de semana de fin
        - year (int, optional): Año para el cual obtener los datos
        - start_hour (int, optional): Hora de inicio del rango (default: 7)
        - end_hour (int, optional): Hora de fin del rango (default: 3)

        Returns:
        - JSON confirmando el envío del email
        """
        try:
            # Obtener parámetros del body
            dia = request.data.get('dia')
            start_week = request.data.get('start_week')
            end_week = request.data.get('end_week')
            year = request.data.get('year')
            start_hour = request.data.get('start_hour', 7)
            end_hour = request.data.get('end_hour', 3)

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
                start_hour = int(start_hour)
                end_hour = int(end_hour)
            except ValueError:
                return Response(
                    {'error': 'Los parámetros numéricos deben ser enteros válidos'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Validar rangos de horas
            if start_hour < 0 or start_hour > 23:
                return Response(
                    {'error': 'start_hour debe estar entre 0 y 23'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if end_hour < 0 or end_hour > 23:
                return Response(
                    {'error': 'end_hour debe estar entre 0 y 23'},
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
                command_description = f"Envío de Reporte por Email - Día: {self._get_dia_nombre(dia)}"
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
                'message': f'Reporte enviado por email exitosamente para el día {self._get_dia_nombre(dia)}',
                'parameters': {
                    'dia': dia,
                    'dia_nombre': self._get_dia_nombre(dia),
                    'start_week': start_week,
                    'end_week': end_week,
                    'year': year or datetime.now().year,
                    'start_hour': start_hour,
                    'end_hour': end_hour
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

    def _get_dia_nombre(self, dia):
        """Convierte número de día a nombre"""
        dias_nombres = {
            1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
            5: "Viernes", 6: "Sábado", 7: "Domingo"
        }
        return dias_nombres.get(dia, "Desconocido")
