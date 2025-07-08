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

    def is_in_operating_hours(self, current_datetime):
        """
        Valida si el comando puede ejecutarse según los horarios de operación por día
        Lunes: 12:00-23:00
        Martes: 09:00-23:00
        Miércoles: 09:00-24:00
        Jueves: 09:00-01:00 (del día siguiente)
        Viernes: 08:00-02:00 (del día siguiente)
        Sábado: 08:00-02:00 (del día siguiente)
        Domingo: 08:00-22:00
        """
        day_of_week = current_datetime.isoweekday()  # 1=lunes, 7=domingo
        current_hour = current_datetime.hour

        if day_of_week == 1:  # Lunes
            return 12 <= current_hour <= 23
        elif day_of_week == 2:  # Martes
            return 9 <= current_hour <= 23
        elif day_of_week == 3:  # Miércoles
            # hasta 24:00 (00:00 del día siguiente)
            return 9 <= current_hour <= 23 or current_hour == 0
        elif day_of_week == 4:  # Jueves
            # hasta 01:00 del día siguiente
            return 9 <= current_hour <= 23 or current_hour == 0 or current_hour == 1
        elif day_of_week == 5:  # Viernes
            # hasta 02:00 del día siguiente
            return 8 <= current_hour <= 23 or current_hour == 0 or current_hour == 1 or current_hour == 2
        elif day_of_week == 6:  # Sábado
            # hasta 02:00 del día siguiente
            return 8 <= current_hour <= 23 or current_hour == 0 or current_hour == 1 or current_hour == 2
        elif day_of_week == 7:  # Domingo
            return 8 <= current_hour <= 22

        return False

    def handle(self, *args, **options):

        guayaquil_time = self.get_guayaquil_time()
        current_date = guayaquil_time.date()
        current_time = guayaquil_time.time()

        # Validar horarios de operación por día de la semana
        if not self.is_in_operating_hours(guayaquil_time):
            day_names = {
                1: 'Lunes', 2: 'Martes', 3: 'Miércoles', 4: 'Jueves',
                5: 'Viernes', 6: 'Sábado', 7: 'Domingo'
            }
            day_schedules = {
                1: '12:00-23:00',
                2: '09:00-23:00',
                3: '09:00-24:00',
                4: '09:00-01:00',
                5: '08:00-02:00',
                6: '08:00-02:00',
                7: '08:00-22:00'
            }

            day_of_week = guayaquil_time.isoweekday()
            self.stdout.write(
                self.style.WARNING(
                    f'Comando ejecutado fuera del horario de operación. '
                    f'Día: {day_names[day_of_week]} ({day_schedules[day_of_week]}). '
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
