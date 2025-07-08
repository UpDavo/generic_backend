from django.core.management.base import BaseCommand
from django.utils import timezone
import pytz
from tada.models import ExecutionLog, TrafficEvent, TrafficLog
from tada.services.braze_service import BrazeService
from tada.services.report_service import ReportService
from tada.utils.constants import APPS


class Command(BaseCommand):
    help = 'Comando para obtener datos de órdenes por hora y crear logs automáticos'

    def get_guayaquil_time(self):
        """Obtiene la fecha y hora actual en zona horaria de Guayaquil, Ecuador"""
        guayaquil_tz = pytz.timezone('America/Guayaquil')
        return timezone.now().astimezone(guayaquil_tz)

    def handle(self, *args, **options):

        guayaquil_time = self.get_guayaquil_time()
        current_date = guayaquil_time.date()
        current_time = guayaquil_time.time()

        current_hour = current_time.hour
        if not (current_hour >= 7 or current_hour < 3):
            self.stdout.write(
                self.style.WARNING(
                    f'Comando ejecutado fuera del rango permitido (7 AM - 3 AM). '
                    f'Hora actual: {current_time.strftime("%H:%M")}. No se procesarán datos.'
                )
            )
            return

        try:
            # Obtener la fecha y hora actual en Guayaquil
            braze_service = BrazeService()
            report_service = ReportService()

            event = TrafficEvent.objects.get(id=2)

            # Validar que esté en el rango horario permitido (7 AM - 3 AM del día siguiente)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Procesando datos para {current_date} a las {current_time} (Guayaquil)'
                )
            )
            # Obtener los eventos de ahora
            response = braze_service.get_data_series(
                event_id=event.braze_id, length=1)

            # El servicio devuelve una tupla (data, http_response)
            if isinstance(response, tuple):
                data, http_response = response
            else:
                data = response

            if not data or 'data' not in data or not data['data']:
                self.stdout.write(
                    self.style.WARNING('No se encontraron datos para procesar')
                )
                return

            count = data['data'][0].get('count', 0)
            event_time = data['data'][0].get('time', 'N/A')

            self.stdout.write(
                self.style.SUCCESS(
                    f'Datos obtenidos exitosamente: {count} eventos para {event_time}')
            )

            # Crear los logs de trafico
            TrafficLog.objects.create(
                event=event,
                date=current_date,
                time=current_time,
                count=count,
                app=APPS['TRAFFIC']
            )

            # Crear el log de ejecución
            ExecutionLog.objects.create(
                event=event,
                execution_type='automatic',
                command='Obtención Automática de Datos por Hora',
                date=current_date,
                time=current_time,
                app=APPS['EXECUTION']
            )

            # Calcular el día de la semana donde lunes=1 y domingo=7
            # Python: lunes=0, domingo=6
            dia_seleccionado = current_date.isoweekday()  # lunes=1, domingo=7
            report_service.send_report_by_email(
                dia_seleccionado=dia_seleccionado)

            self.stdout.write(
                self.style.SUCCESS(
                    f'Logs creados exitosamente para el evento {event.id}'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al procesar datos: {str(e)}')
            )
            raise e
