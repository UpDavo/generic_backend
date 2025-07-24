from django.core.management.base import BaseCommand
from django.utils import timezone
import pytz
from tada.models import TrafficEvent
from tada.services.report_service import ReportService


class Command(BaseCommand):
    help = 'Comando para obtener datos de órdenes por hora y crear logs automáticos'

    def get_guayaquil_time(self):
        guayaquil_tz = pytz.timezone('America/Guayaquil')
        return timezone.now().astimezone(guayaquil_tz)

    def handle(self, *args, **options):

        report_service = ReportService()

        try:
            # Obtener la fecha y hora actual en Guayaquil
            guayaquil_time = self.get_guayaquil_time()
            current_date = guayaquil_time.date()
            current_time = guayaquil_time.time()

            self.stdout.write(
                self.style.SUCCESS(
                    f'Procesando datos para {current_date} a las {current_time} (Guayaquil)'
                )
            )

            # report_service.send_report_by_email(dia_seleccionado=4)
            report_service.send_report_by_whatsapp(dia_seleccionado=4)

        except TrafficEvent.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    'Error: No se encontró el evento de tráfico con ID 2')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al procesar datos: {str(e)}')
            )
            raise e
