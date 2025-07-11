from django.utils import timezone
from datetime import timedelta, time
import pytz
from tada.models import ExecutionLog, TrafficEvent, TrafficLog
from tada.services.braze_service import BrazeService
from tada.services.report_service import ReportService
from tada.utils.constants import APPS, START_WINDOW, END_WINDOW, OPERATING_HOURS, DAY_NAMES, DAY_SCHEDULES


def get_guayaquil_time(self):
    """Obtiene la fecha y hora actual en zona horaria de Guayaquil, Ecuador"""
    guayaquil_tz = pytz.timezone('America/Guayaquil')
    return timezone.now().astimezone(guayaquil_tz)


def get_adjusted_time_for_window(self, current_datetime):
    current_minute = current_datetime.minute
    current_hour = current_datetime.hour
    current_date = current_datetime.date()

    # Aplicar la misma lógica que en ReportService usando constantes
    if current_minute >= START_WINDOW:
        # Si está en o después del minuto de inicio de ventana, pertenece a la siguiente hora
        target_hour = (current_hour + 1) % 24

        # Si la hora ajustada es 0 (medianoche), significa que pasamos al día siguiente
        if target_hour == 0:
            current_date = current_date + timedelta(days=1)

    elif current_minute <= END_WINDOW:
        # Si está en o antes del minuto de fin de ventana, pertenece a la hora actual
        target_hour = current_hour
    else:
        # Si está fuera de la ventana, usar hora actual (no debería pasar con cron a los 57 minutos)
        target_hour = current_hour

    # Crear la hora ajustada (siempre en punto: :00)
    adjusted_time = time(hour=target_hour, minute=0, second=0)

    return current_date, adjusted_time


def is_in_operating_hours(self, current_datetime):
    day_of_week = current_datetime.isoweekday()  # 1=lunes, 7=domingo
    current_hour = current_datetime.hour

    if day_of_week not in OPERATING_HOURS:
        return False

    schedule = OPERATING_HOURS[day_of_week]
    start_hour = schedule['start_hour']
    end_hour = schedule['end_hour']
    crosses_midnight = schedule['crosses_midnight']

    if not crosses_midnight:
        # Horario normal (no cruza medianoche)
        return start_hour <= current_hour <= end_hour
    else:
        # Horario que cruza medianoche
        return current_hour >= start_hour or current_hour <= end_hour


def execute_fetch():

    guayaquil_time = get_guayaquil_time()
    current_date = guayaquil_time.date()
    current_time = guayaquil_time.time()

    # Validar horarios de operación por día de la semana
    if not is_in_operating_hours(guayaquil_time):
        day_of_week = guayaquil_time.isoweekday()
        return

    try:
        # Obtener la fecha y hora actual en Guayaquil
        braze_service = BrazeService()
        report_service = ReportService()

        event = TrafficEvent.objects.get(id=2)

        # Obtener las horas ajustadas según la ventana de tiempo
        adjusted_date, adjusted_time = get_adjusted_time_for_window(
            guayaquil_time)
        # Obtener los eventos de ahora
        response = braze_service.get_data_series(
            event_id=event.braze_id, length=1)

        # El servicio devuelve una tupla (data, http_response)
        if isinstance(response, tuple):
            data, http_response = response
        else:
            data = response

        if not data or 'data' not in data or not data['data']:
            return

        count = data['data'][0].get('count', 0)

        # Crear los logs de trafico usando la hora ajustada
        TrafficLog.objects.create(
            event=event,
            date=adjusted_date,
            time=adjusted_time,
            count=count,
            app=APPS['TRAFFIC']
        )

        # Crear el log de ejecución usando la hora real de ejecución
        ExecutionLog.objects.create(
            event=event,
            execution_type='automatic',
            command='Obtención Automática de Datos por Hora',
            date=current_date,
            time=current_time,
            app=APPS['EXECUTION']
        )
        dia_seleccionado = current_date.isoweekday()
        report_service.send_report_by_email(
            dia_seleccionado=dia_seleccionado)
    except Exception as e:
        print(f"Error al ejecutar el comando: {e}")
        raise e
