from django.utils import timezone
from datetime import timedelta, time
import pytz
from tada.models import ExecutionLog, TrafficEvent, TrafficLog
from tada.services.braze_service import BrazeService
from tada.services.report_service import ReportService
from tada.utils.constants import APPS, START_WINDOW, END_WINDOW, OPERATING_HOURS, DAY_NAMES, DAY_SCHEDULES


def get_guayaquil_time():
    """Obtiene la fecha y hora actual en zona horaria de Guayaquil, Ecuador"""
    guayaquil_tz = pytz.timezone('America/Guayaquil')
    return timezone.now().astimezone(guayaquil_tz)


def get_adjusted_time_for_window(current_datetime):
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


def is_in_operating_hours(current_datetime):
    day_of_week = current_datetime.isoweekday()  # 1=lunes, 7=domingo
    current_hour = current_datetime.hour

    # Primero verificar si estamos en horas tempranas que podrían pertenecer al día anterior
    if current_hour <= 6:  # Horas de madrugada (00:00 - 06:00)
        # Verificar si el día anterior tiene horario que cruza medianoche
        previous_day = 7 if day_of_week == 1 else day_of_week - 1
        if previous_day in OPERATING_HOURS:
            prev_schedule = OPERATING_HOURS[previous_day]
            # Solo considerar válido si el día anterior cruza medianoche Y estamos dentro del rango de fin
            if prev_schedule['crosses_midnight'] and current_hour <= prev_schedule['end_hour']:
                print(
                    f"DEBUG: Horario válido - {DAY_NAMES[previous_day]} ({DAY_SCHEDULES[previous_day]}) se extiende hasta las {current_hour:02d}:00")
                return True

    # Verificar horario del día actual
    if day_of_week not in OPERATING_HOURS:
        return False

    schedule = OPERATING_HOURS[day_of_week]
    start_hour = schedule['start_hour']
    end_hour = schedule['end_hour']
    crosses_midnight = schedule['crosses_midnight']

    if not crosses_midnight:
        # Horario normal (no cruza medianoche)
        is_valid = start_hour <= current_hour <= end_hour
        if is_valid:
            print(
                f"DEBUG: Horario válido - {DAY_NAMES[day_of_week]} ({DAY_SCHEDULES[day_of_week]}) - hora actual: {current_hour:02d}:00")
        return is_valid
    else:
        # Horario que cruza medianoche - solo verificar el inicio
        is_valid = current_hour >= start_hour
        if is_valid:
            print(
                f"DEBUG: Horario válido - {DAY_NAMES[day_of_week]} ({DAY_SCHEDULES[day_of_week]}) - hora actual: {current_hour:02d}:00")
        return is_valid


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


def execute_fetch_simple():

    guayaquil_time = get_guayaquil_time()
    current_date = guayaquil_time.date()
    current_time = guayaquil_time.time()

    # Sin validaciones de horario - toma datos a cualquier hora

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
            command='Obtención Automática de Datos por Hora - Simple',
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


def debug_operating_hours():
    """Función de debug para verificar horarios de operación"""
    from datetime import datetime

    # Casos de prueba específicos
    test_cases = [
        # Sábado 08:00 - debería ser válido (inicio del horario)
        (6, 8, "Sábado 08:00 - inicio horario"),
        # Sábado 15:00 - debería ser válido (medio día)
        (6, 15, "Sábado 15:00 - medio día"),
        # Sábado 23:00 - debería ser válido (antes de medianoche)
        (6, 23, "Sábado 23:00 - antes medianoche"),
        # Domingo 01:00 - debería ser válido (extensión del sábado)
        (7, 1, "Domingo 01:00 - extensión sábado"),
        # Domingo 02:00 - debería ser válido (fin del horario del sábado)
        (7, 2, "Domingo 02:00 - fin horario sábado"),
        # Domingo 03:00 - NO debería ser válido (fuera del horario)
        (7, 3, "Domingo 03:00 - fuera de horario"),
        # Domingo 08:00 - debería ser válido (inicio del domingo)
        (7, 8, "Domingo 08:00 - inicio domingo"),
    ]

    print("=== DEBUG: Verificación de horarios de operación ===")
    print("Horarios configurados:")
    for day in range(1, 8):
        if day in DAY_SCHEDULES:
            print(f"  {DAY_NAMES[day]}: {DAY_SCHEDULES[day]}")
    print("\nValidaciones:")

    for day, hour, description in test_cases:
        # Crear un datetime ficticio para la prueba
        test_time = datetime(2024, 1, 1, hour, 0, 0)  # Fecha ficticia
        test_time = test_time.replace(
            weekday=day-1)  # Ajustar día de la semana

        # Simular el isoweekday manualmente
        class MockDateTime:
            def __init__(self, day_of_week, hour):
                self.day_of_week = day_of_week
                self.hour = hour

            def isoweekday(self):
                return self.day_of_week

        mock_dt = MockDateTime(day, hour)
        result = is_in_operating_hours(mock_dt)

        status = "✅ VÁLIDO" if result else "❌ NO VÁLIDO"
        print(f"{description}: {status}")

    print("=== Fin verificación ===")
