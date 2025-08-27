from datetime import datetime, timedelta
from tada.models.trafficLog import TrafficLog
from tada.models.dailyMeta import DailyMeta
from core.utils.emailThread import EmailThread
from core.models import EmailNotification, EmailNotificationType
from core.services.whatsapp_service import WhatsAppService
from core.utils.html_to_image import HTMLToImageService
from tada.utils.constants import START_WINDOW, END_WINDOW, DAY_NAMES, OPERATING_HOURS


class ReportService:
    # Configuración de ventana de tiempo para registros
    # Registros entre START_WINDOW de una hora hasta END_WINDOW de la siguiente hora
    # se consideran datos de la hora siguiente
    START_WINDOW_MINUTE = START_WINDOW  # Importado desde constants
    END_WINDOW_MINUTE = END_WINDOW      # Importado desde constants

    def get_datetime_variation(self, dia, start_week=None, end_week=None, year=None, start_hour=None, end_hour=None):
        """
        Obtiene la variación de tráfico por hora durante un rango de semanas para un día específico.

        Utiliza una ventana de tiempo configurable (START_WINDOW_MINUTE a END_WINDOW_MINUTE) 
        para determinar a qué hora pertenecen los registros.

        Los horarios de operación se obtienen automáticamente de OPERATING_HOURS según el día,
        considerando si el horario se extiende al día siguiente.

        Args:
            dia (int): Día de la semana (1=Lunes, 2=Martes, 3=Miércoles, 4=Jueves, 5=Viernes, 6=Sábado, 7=Domingo)
            start_week (int): Número de semana de inicio (opcional, default: 4 semanas antes de la actual)
            end_week (int): Número de semana de fin (opcional, default: semana actual)
            year (int): Año para el cual obtener los datos (opcional, default: año actual)
            start_hour (int): Hora de inicio del rango (opcional, se obtiene de OPERATING_HOURS si no se especifica)
            end_hour (int): Hora de fin del rango (opcional, se obtiene de OPERATING_HOURS si no se especifica)

        Returns:
            dict: Diccionario con datos de tráfico por hora, variación diaria y comparación con meta

        Note:
            La ventana de tiempo se configura con START_WINDOW_MINUTE y END_WINDOW_MINUTE.
            Por defecto: registros entre minuto 57 de una hora hasta minuto 3 de la siguiente
            se consideran datos de la hora siguiente (ej: 8:57-9:03 → datos de las 9:00)

            Los horarios se obtienen de OPERATING_HOURS:
            - Lunes: 12:00-23:00
            - Martes: 09:00-23:00  
            - Miércoles: 09:00-24:00
            - Jueves: 09:00-01:00 (del día siguiente)
            - Viernes: 08:00-02:00 (del día siguiente)
            - Sábado: 08:00-02:00 (del día siguiente)
            - Domingo: 08:00-22:00
        """
        BASE_WEEKS = 4
        # Validar el parámetro día
        if dia is None or not isinstance(dia, int) or dia < 1 or dia > 7:
            raise ValueError(
                "El parámetro 'dia' es obligatorio y debe ser un entero entre 1 (Lunes) y 7 (Domingo)")

        # Obtener el año actual
        current_year = datetime.now().year
        current_week = datetime.now().isocalendar()[1]

        # Establecer el año (usar el actual si no se proporciona)
        target_year = year if year is not None else current_year

        # Establecer valores por defecto si no se proporcionan
        if end_week is None:
            end_week = current_week
        if start_week is None:
            # 7 semanas anteriores + la actual = 8 semanas total
            start_week = max(1, end_week - BASE_WEEKS)

        # Obtener horarios de operación para el día especificado
        if start_hour is None or end_hour is None:
            day_schedule = OPERATING_HOURS.get(dia)
            if day_schedule:
                if start_hour is None:
                    start_hour = day_schedule['start_hour']
                if end_hour is None:
                    end_hour = day_schedule['end_hour']
            else:
                # Valores por defecto si no se encuentra el día
                start_hour = start_hour or 7
                end_hour = end_hour or 3
        # Calcular fechas de inicio y fin basadas en las semanas ISO

        def get_week_start_end(year, week):
            """Obtiene el primer y último día de una semana ISO"""
            jan4 = datetime(year, 1, 4)
            start = jan4 + timedelta(days=jan4.weekday() * -1, weeks=week-1)
            end = start + timedelta(days=6)
            return start.date(), end.date()

        start_date, _ = get_week_start_end(target_year, start_week)
        _, end_date = get_week_start_end(target_year, end_week)

        # Crear lista de horas válidas basada en el rango especificado
        valid_hours = []
        if start_hour <= end_hour:
            # Rango normal (ej: 07:00 a 22:00)
            valid_hours = list(range(start_hour, end_hour + 1))
        else:
            # Rango que cruza medianoche (ej: 07:00 a 03:00 del día siguiente)
            valid_hours = list(range(start_hour, 24)) + \
                list(range(0, end_hour + 1))

        # Obtener registros del día especificado y del día siguiente si el rango cruza medianoche
        if start_hour > end_hour:
            # Rango que cruza medianoche: necesitamos registros del día actual y el siguiente
            next_day = dia + 1 if dia < 7 else 1

            # Convertir a formato Django para ambos días
            django_weekday = dia + 1 if dia < 7 else 1
            django_weekday_next = next_day + 1 if next_day < 7 else 1

            traffic_logs = TrafficLog.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
                date__week_day__in=[django_weekday, django_weekday_next]
            ).order_by('date', 'time')
        else:
            # Rango normal: solo el día especificado
            django_weekday = dia + 1 if dia < 7 else 1

            traffic_logs = TrafficLog.objects.filter(
                date__gte=start_date,
                date__lte=end_date,
                date__week_day=django_weekday
            ).order_by('date', 'time')

        # Diccionario para almacenar los datos por hora y semana
        hourly_data = {}

        # Procesar registros aplicando ventana de tiempo:
        # Registros entre START_WINDOW_MINUTE de una hora hasta END_WINDOW_MINUTE de la siguiente hora
        # se consideran datos de la hora siguiente (ej: 57-3 → 8:57-9:03 = datos de las 9:00)
        for log in traffic_logs:
            # Aplicar ventana de tiempo: registros entre minuto START_WINDOW_MINUTE de una hora hasta minuto END_WINDOW_MINUTE de la siguiente
            # se consideran de la hora siguiente
            actual_hour = log.time.hour
            actual_minute = log.time.minute

            # Determinar a qué hora pertenece este registro según la ventana
            if actual_minute >= self.START_WINDOW_MINUTE:
                # Si está en o después del minuto de inicio de ventana, pertenece a la siguiente hora
                target_hour = (actual_hour + 1) % 24
            elif actual_minute <= self.END_WINDOW_MINUTE:
                # Si está en o antes del minuto de fin de ventana, pertenece a la hora actual
                target_hour = actual_hour
            else:
                # Si está fuera de la ventana, saltar este registro
                continue

            hour_key = f"{target_hour:02d}:00"

            # Obtener el día de la semana del registro (1=Lunes, 7=Domingo)
            log_weekday = log.date.isoweekday()

            # Verificar si el registro es válido para nuestro rango de tiempo
            is_valid_record = False

            if start_hour <= end_hour:
                # Rango normal: solo registros del día especificado
                if log_weekday == dia and target_hour in valid_hours:
                    is_valid_record = True
            else:
                # Rango que cruza medianoche
                if log_weekday == dia:
                    # Registros del día principal (desde start_hour hasta 23)
                    if target_hour >= start_hour:
                        is_valid_record = True
                else:
                    # Calcular el día siguiente
                    next_day = dia + 1 if dia < 7 else 1
                    if log_weekday == next_day:
                        # Registros del día siguiente (desde 0 hasta end_hour)
                        if target_hour <= end_hour:
                            is_valid_record = True

            if not is_valid_record:
                continue

            # Obtener el número de semana
            week_number = log.date.isocalendar()[1]

            # Inicializar estructura si no existe
            if hour_key not in hourly_data:
                hourly_data[hour_key] = {}

            if week_number not in hourly_data[hour_key]:
                hourly_data[hour_key][week_number] = []

            # Agregar el registro con timestamp completo para ordenamiento
            hourly_data[hour_key][week_number].append({
                'time': log.time,
                'count': log.count,
                'datetime': datetime.combine(log.date, log.time)
            })

        # Procesar los datos para obtener el registro más tardío por hora/semana
        result = []

        for hour_key, weeks_data in hourly_data.items():
            hour_result = {
                "hora": hour_key,
                "semanas": {},
                "variacion": 0
            }

            counts_for_variation = []

            for week_num in range(start_week, end_week + 1):
                if week_num in weeks_data:
                    # Obtener el registro más tardío de la hora usando la nueva ventana de tiempo
                    hour_int = int(hour_key.split(':')[0])

                    # Filtrar registros dentro de la ventana de tiempo configurada
                    # Los registros ya están filtrados por la ventana en el procesamiento anterior
                    valid_records = []
                    for record in weeks_data[week_num]:
                        # Los registros ya están asignados a la hora correcta según la ventana
                        # Solo verificar que correspondan a la hora que estamos procesando
                        record_hour = record['time'].hour
                        record_minute = record['time'].minute

                        # Determinar a qué hora pertenece este registro según la ventana configurada
                        if record_minute >= self.START_WINDOW_MINUTE:
                            target_record_hour = (record_hour + 1) % 24
                        elif record_minute <= self.END_WINDOW_MINUTE:
                            target_record_hour = record_hour
                        else:
                            continue  # No debería llegar aquí ya que se filtró antes

                        # Si coincide con la hora que estamos procesando, es válido
                        if target_record_hour == hour_int:
                            valid_records.append(record)

                    if valid_records:
                        # Obtener el registro más tardío dentro de la ventana
                        latest_record = max(
                            valid_records, key=lambda x: x['datetime'])
                        hour_result["semanas"][str(
                            week_num)] = latest_record['count']
                        counts_for_variation.append(latest_record['count'])
                    else:
                        hour_result["semanas"][str(week_num)] = 0
                        counts_for_variation.append(0)
                else:
                    hour_result["semanas"][str(week_num)] = 0
                    counts_for_variation.append(0)

            # Calcular la variación porcentual
            if len(counts_for_variation) > 1:
                # Fórmula: (Semana_actual - Semana_anterior) / Semana_anterior * 100
                # Penúltima semana
                penultimate_value = counts_for_variation[-2]
                # Última semana (actual)
                last_value = counts_for_variation[-1]

                if penultimate_value > 0:
                    variation_percentage = int(
                        ((last_value - penultimate_value) / penultimate_value) * 100)
                else:
                    # Si la penúltima semana es 0, calcular como crecimiento infinito o 0
                    if last_value > 0:
                        variation_percentage = 100  # Crecimiento del 100% cuando no había datos anteriores
                    else:
                        variation_percentage = 0
            else:
                variation_percentage = 0

            hour_result["variacion"] = variation_percentage
            result.append(hour_result)

        # Ordenar por hora considerando el rango especificado
        def sort_key(item):
            hour = int(item["hora"].split(':')[0])
            # Si el rango cruza medianoche, ajustar el orden
            if start_hour > end_hour:
                if hour >= start_hour:
                    return hour
                else:
                    return hour + 24
            return hour

        result.sort(key=sort_key)

        # Calcular variación total del día (todas las horas) vs semana anterior
        daily_variation = self._calculate_daily_variation(
            result, start_week, end_week, dia, start_hour, end_hour)

        # Calcular comparación con meta diaria si es posible (optimizado)
        daily_meta_vs_real = None
        if result:
            # Obtener semanas únicas desde los datos de resultado (optimizado)
            weeks = set()
            for row in result:
                weeks.update(row["semanas"].keys())
            weeks = sorted([int(w) for w in weeks])

            if weeks:
                # Obtener la fecha más reciente de la semana actual
                current_week = max(weeks)
                today = datetime.now().date()

                # Buscar una fecha que corresponda al día especificado en la semana actual
                target_date = None
                for i in range(7):  # Buscar en los últimos 7 días
                    check_date = today - timedelta(days=i)
                    if check_date.isoweekday() == dia:
                        target_date = check_date
                        break

                if target_date:
                    try:
                        # Usar método optimizado que no hace llamadas recursivas
                        daily_meta_vs_real = self._get_daily_meta_vs_real_optimized(
                            date=target_date,
                            hourly_data=result,
                            target_week=current_week,
                            dia=dia,
                            start_hour=start_hour,
                            end_hour=end_hour
                        )
                    except Exception as e:
                        # Si hay error, solo loguear pero no fallar
                        print(
                            f"Error al obtener comparación meta vs real: {e}")
                        daily_meta_vs_real = None

        return {
            'hourly_data': result,
            'daily_variation': daily_variation,
            'daily_meta_vs_real': daily_meta_vs_real,
            'current_time': self._get_current_time_summary(result, start_week, end_week, dia, start_hour, end_hour)
        }

    def _get_current_time_summary(self, hourly_data, start_week, end_week, dia, start_hour, end_hour):
        """
        Obtiene un resumen del estado actual comparando semana pasada vs actual.
        Usa la misma hora (última hora con datos de semana actual) para ambas semanas.

        Considera los horarios de operación dinámicos según el día especificado.

        Args:
            hourly_data (list): Datos por hora procesados
            start_week (int): Semana de inicio
            end_week (int): Semana de fin
            dia (int): Día de la semana (1=Lunes, 7=Domingo)
            start_hour (int): Hora de inicio del rango de operación
            end_hour (int): Hora de fin del rango de operación

        Returns:
            dict: Resumen con datos de semana pasada, actual, última hora y variación
        """
        # Obtener todas las semanas disponibles
        weeks = list(range(start_week, end_week + 1))

        # Si no hay suficientes semanas, retornar valores por defecto
        if len(weeks) < 2:
            return {
                'w_pasada': 0,
                'w_actual': 0,
                'ultima_hora_toma_datos_w_actual': None,
                'fecha': datetime.now().date().strftime('%Y-%m-%d'),
                'variacion': 0
            }

        # Obtener las dos últimas semanas
        w_actual = weeks[-1]
        w_pasada = weeks[-2]
        w_actual_str = str(w_actual)
        w_pasada_str = str(w_pasada)

        # PASO 1: Encontrar la última hora con datos en la semana actual
        # Considerando los horarios de operación del día especificado
        w_actual_count = 0
        ultima_hora_datos = None

        # Crear lista de horas válidas según los horarios de operación
        valid_operating_hours = []
        if start_hour <= end_hour:
            # Rango normal (ej: 12:00 a 23:00)
            valid_operating_hours = list(range(start_hour, end_hour + 1))
        else:
            # Rango que cruza medianoche (ej: 09:00 a 01:00 del día siguiente)
            valid_operating_hours = list(
                range(start_hour, 24)) + list(range(0, end_hour + 1))

        # Ordenar las horas de mayor a menor para encontrar la última hora del día
        # Las horas de 0 a 3 AM son las más tardías del día cuando cruza medianoche
        def sort_hour_key(hour):
            if start_hour > end_hour:  # Si cruza medianoche
                if 0 <= hour <= end_hour:  # Horas de madrugada (más tardías)
                    return hour + 24
                else:  # Horas normales del día
                    return hour
            else:
                return hour

        # Filtrar solo los datos que están dentro del horario de operación y ordenar
        valid_hours_with_data = []
        for hour_data in hourly_data:
            hour_int = int(hour_data['hora'].split(':')[0])
            if hour_int in valid_operating_hours:
                valid_hours_with_data.append((hour_int, hour_data))

        # Ordenar por hora de mayor a menor (considerando cruce de medianoche)
        valid_hours_with_data.sort(
            key=lambda x: sort_hour_key(x[0]), reverse=True)

        # Buscar la última hora con datos en la semana actual
        for hour_int, hour_data in valid_hours_with_data:
            if w_actual_str in hour_data['semanas'] and hour_data['semanas'][w_actual_str] > 0:
                w_actual_count = hour_data['semanas'][w_actual_str]
                ultima_hora_datos = hour_data['hora']
                break

        # PASO 2: Usar esa MISMA hora para obtener datos de la semana pasada
        w_pasada_count = 0

        if ultima_hora_datos:
            # Buscar específicamente esa hora en la semana pasada
            for hour_data in hourly_data:
                if hour_data['hora'] == ultima_hora_datos:
                    w_pasada_count = hour_data['semanas'].get(w_pasada_str, 0)
                    break

        # Calcular variación porcentual
        variacion = 0
        if w_pasada_count > 0:
            variacion = int(
                ((w_actual_count - w_pasada_count) / w_pasada_count) * 100)
        elif w_actual_count > 0:
            variacion = 100  # Crecimiento del 100% cuando no había datos anteriores

        return {
            'w_pasada': w_pasada_count,
            'w_actual': w_actual_count,
            'ultima_hora_toma_datos_w_actual': ultima_hora_datos,
            'fecha': datetime.now().date().strftime('%Y-%m-%d'),
            'variacion': variacion
        }

    def _calculate_daily_variation(self, hourly_data, start_week, end_week, dia, start_hour, end_hour):
        """
        Calcula la variación total del día completo comparando la semana actual vs la semana anterior.

        Toma el último registro del día para cada semana independientemente:
        - Semana actual: último registro disponible (ej: 10:00 con 2)
        - Semana anterior: último registro disponible (ej: 23:00 con 394)

        Cada registro de hora es un total acumulado, no un incremento.
        Usa los horarios de operación dinámicos según el día especificado.

        Args:
            hourly_data (list): Datos por hora procesados
            start_week (int): Semana de inicio
            end_week (int): Semana de fin
            dia (int): Día de la semana (1=Lunes, 7=Domingo)
            start_hour (int): Hora de inicio del rango de operación
            end_hour (int): Hora de fin del rango de operación

        Returns:
            dict: Diccionario con variación diaria y totales por semana
        """
        # Obtener todas las semanas disponibles
        weeks = list(range(start_week, end_week + 1))

        # Si no hay suficientes semanas para comparar, retornar valores por defecto
        if len(weeks) < 2:
            return {
                'weekly_totals': {},
                'variation_percentage': 0,
                'current_week_total': 0,
                'previous_week_total': 0,
                'comparison_hour': None
            }

        # Obtener las dos últimas semanas para comparar
        current_week = weeks[-1]
        previous_week = weeks[-2]
        current_week_str = str(current_week)
        previous_week_str = str(previous_week)

        # Encontrar el último registro del día para cada semana
        # Usando los horarios de operación dinámicos
        comparison_hour = None
        current_week_total = 0
        previous_week_total = 0

        # Crear lista de horas válidas según los horarios de operación
        valid_operating_hours = []
        if start_hour <= end_hour:
            # Rango normal (ej: 12:00 a 23:00)
            valid_operating_hours = list(range(start_hour, end_hour + 1))
        else:
            # Rango que cruza medianoche (ej: 09:00 a 01:00 del día siguiente)
            valid_operating_hours = list(
                range(start_hour, 24)) + list(range(0, end_hour + 1))

        # Filtrar horas que están dentro del horario de operación y tienen datos
        hours_with_data = []
        for hour_data in hourly_data:
            if (current_week_str in hour_data['semanas'] and hour_data['semanas'][current_week_str] > 0) or \
               (previous_week_str in hour_data['semanas'] and hour_data['semanas'][previous_week_str] > 0):
                hour_int = int(hour_data['hora'].split(':')[0])
                # Solo incluir horas que están dentro del horario de operación
                if hour_int in valid_operating_hours:
                    hours_with_data.append((hour_int, hour_data))

        # Ordenar por hora (considerando el cruce de medianoche)
        def sort_hour_key(item):
            hour = item[0]
            if start_hour > end_hour:  # Si cruza medianoche
                if 0 <= hour <= end_hour:  # Horas de madrugada (más tardías)
                    return hour + 24
                else:  # Horas normales del día
                    return hour
            else:
                return hour

        hours_with_data.sort(key=sort_hour_key, reverse=True)

        # Buscar el último registro del día para cada semana por separado
        # Para semana actual
        current_week_comparison_hour = None
        current_week_total = 0
        current_week_last_hour = None

        for hour_int, hour_data in hours_with_data:
            current_count = hour_data['semanas'].get(current_week_str, 0)
            if current_count > 0:
                current_week_last_hour = hour_int
                current_week_comparison_hour = hour_data['hora']

                # Si la última hora es de madrugada y cruza medianoche, calcular total acumulado
                if start_hour > end_hour and 0 <= hour_int <= end_hour:
                    current_week_total = self._calculate_total_with_dawn_hours(
                        hourly_data, current_week_str, hour_int
                    )
                else:
                    current_week_total = current_count
                break

        # Para semana anterior
        previous_week_comparison_hour = None
        previous_week_total = 0
        previous_week_last_hour = None

        for hour_int, hour_data in hours_with_data:
            previous_count = hour_data['semanas'].get(previous_week_str, 0)
            if previous_count > 0:
                previous_week_last_hour = hour_int
                previous_week_comparison_hour = hour_data['hora']

                # Si la última hora es de madrugada y cruza medianoche, calcular total acumulado
                if start_hour > end_hour and 0 <= hour_int <= end_hour:
                    previous_week_total = self._calculate_total_with_dawn_hours(
                        hourly_data, previous_week_str, hour_int
                    )
                else:
                    previous_week_total = previous_count
                break

        # Usar la hora de la semana actual como referencia para comparación
        # (o la de la semana anterior si no hay datos en la actual)
        comparison_hour = current_week_comparison_hour or previous_week_comparison_hour

        # Calcular totales para todas las semanas (usando el último registro de cada semana)
        weekly_totals = {}
        for week in weeks:
            week_str = str(week)
            week_total = 0
            week_last_hour = None

            # Buscar el último registro del día que tenga datos para esta semana específica
            for hour_int, hour_data in hours_with_data:
                count = hour_data['semanas'].get(week_str, 0)
                if count > 0:
                    week_last_hour = hour_int

                    # Si la última hora es de madrugada y cruza medianoche, calcular total acumulado
                    if start_hour > end_hour and 0 <= hour_int <= end_hour:
                        week_total = self._calculate_total_with_dawn_hours(
                            hourly_data, week_str, hour_int
                        )
                    else:
                        week_total = count
                    break

            weekly_totals[week_str] = week_total

        # Calcular variación entre la última semana y la penúltima
        daily_variation_percentage = 0

        if previous_week_total > 0:
            daily_variation_percentage = int(
                ((current_week_total - previous_week_total) / previous_week_total) * 100
            )
        else:
            # Si la semana anterior es 0, calcular como crecimiento del 100% o 0
            if current_week_total > 0:
                daily_variation_percentage = 100
            else:
                daily_variation_percentage = 0

        return {
            'weekly_totals': weekly_totals,
            'variation_percentage': daily_variation_percentage,
            'current_week_total': current_week_total,
            'previous_week_total': previous_week_total,
            'comparison_hour': comparison_hour,
            'current_week_comparison_hour': current_week_comparison_hour,
            'previous_week_comparison_hour': previous_week_comparison_hour
        }

    def send_report_by_email(self, dia_seleccionado, start_week=None, end_week=None, year=None, start_hour=7, end_hour=3):
        try:
            # Generar el reporte con los parámetros recibidos
            report_data = self.get_datetime_variation(
                dia=dia_seleccionado,
                start_week=start_week,
                end_week=end_week,
                year=year,
                start_hour=start_hour,
                end_hour=end_hour
            )

            # Extraer datos del nuevo formato de respuesta
            result = report_data['hourly_data']
            daily_variation = report_data['daily_variation']
            daily_meta_vs_real = report_data['daily_meta_vs_real']
            current_time = report_data['current_time']

            # Usar constante para nombres de días
            dia_nombre = DAY_NAMES.get(dia_seleccionado, "Desconocido")

            # Optimización: Calcular todos los valores en una sola iteración
            if not result:
                # Manejar caso de datos vacíos
                email_data = {
                    'data': [],
                    'weeks': [],
                    'max_variacion': 1,
                    'dia_nombre': dia_nombre,
                    'total_ordenes_ultima_hora': 0,
                    'daily_variation': daily_variation,
                    'daily_meta_vs_real': daily_meta_vs_real
                }
                subject = f"Tada Ecuador Pedidos {dia_nombre} - Sin datos"
            else:
                # Obtener semanas únicas de manera eficiente
                weeks = set()
                variaciones = []

                for row in result:
                    weeks.update(row["semanas"].keys())
                    if row['variacion'] is not None:
                        variaciones.append(abs(row['variacion']))

                weeks = sorted(int(k) for k in weeks)
                max_variacion = max(variaciones) if variaciones else 1

                # Encontrar la última hora con datos en una sola iteración reversa
                ultima_semana_str = str(max(weeks)) if weeks else None
                total_ordenes_ultima_hora = 0
                ultima_hora_hoy = None

                if ultima_semana_str:
                    for row in reversed(result):
                        if ultima_semana_str in row['semanas'] and row['semanas'][ultima_semana_str] > 0:
                            if total_ordenes_ultima_hora == 0:  # Primera vez que encontramos datos
                                total_ordenes_ultima_hora = row['semanas'][ultima_semana_str]
                                ultima_hora_hoy = row['hora']
                            break

                # Preparar data para el template
                email_data = {
                    'data': result,
                    'weeks': weeks,
                    'max_variacion': max_variacion,
                    'dia_nombre': dia_nombre,
                    'total_ordenes_ultima_hora': total_ordenes_ultima_hora,
                    'daily_variation': daily_variation,
                    'daily_meta_vs_real': daily_meta_vs_real,
                    'current_time': current_time
                }

                # print(email_data)

                # Crear el subject dinámico
                subject = f"Tada Ecuador Pedidos {dia_nombre}"
                if ultima_hora_hoy:
                    subject += f" - {ultima_hora_hoy}"

            # Verificar si hay emails configurados antes de enviar
            emails_configurados = EmailNotification.get_emails_by_type_constant(
                notification_type_constant=EmailNotificationType.TRAFFIC_REPORT
            )
            emails_configurados = list(emails_configurados)

            if not emails_configurados:
                print("No hay emails configurados para recibir reportes de tráfico")
                return

            # Enviar el correo usando el nuevo método con TRAFFIC_REPORT
            EmailNotification.send_notification_by_type_constant(
                email_template='email/hourly_variation.html',
                subject=subject,
                email_data=email_data,
                notification_type_constant=EmailNotificationType.TRAFFIC_REPORT
            )

        except Exception as e:
            print(f"Error al enviar el reporte por email: {e}")

    def send_report_by_whatsapp(self, dia_seleccionado, start_week=None, end_week=None, year=None, start_hour=7, end_hour=3):
        """
        Envía el reporte de tráfico por WhatsApp usando el servicio de WhatsApp.
        Genera una imagen a partir del template HTML y la envía como adjunto.

        Args:
            dia_seleccionado (int): Día de la semana (1=Lunes, 7=Domingo)
            start_week (int): Semana de inicio (opcional)
            end_week (int): Semana de fin (opcional)
            year (int): Año (opcional)
            start_hour (int): Hora de inicio (opcional)
            end_hour (int): Hora de fin (opcional)
        """
        html_to_image_service = HTMLToImageService()
        whatsapp_service = WhatsAppService()
        image_url = None

        try:
            # Generar el reporte con los parámetros recibidos
            report_data = self.get_datetime_variation(
                dia=dia_seleccionado,
                start_week=start_week,
                end_week=end_week,
                year=year,
                start_hour=start_hour,
                end_hour=end_hour
            )

            # Extraer datos del nuevo formato de respuesta
            result = report_data['hourly_data']
            daily_variation = report_data['daily_variation']
            daily_meta_vs_real = report_data['daily_meta_vs_real']
            current_time = report_data['current_time']

            # Usar constante para nombres de días
            dia_nombre = DAY_NAMES.get(dia_seleccionado, "Desconocido")

            # Optimización: Calcular todos los valores en una sola iteración
            if not result:
                # Manejar caso de datos vacíos
                whatsapp_data = {
                    'data': [],
                    'weeks': [],
                    'max_variacion': 1,
                    'dia_nombre': dia_nombre,
                    'total_ordenes_ultima_hora': 0,
                    'daily_variation': daily_variation,
                    'daily_meta_vs_real': daily_meta_vs_real,
                    'current_time': current_time
                }

                # Generar imagen desde el template HTML
                image_url = html_to_image_service.generate_image_from_template(
                    template_path='email/hourly_variation.html',
                    context_data=whatsapp_data
                )

                # Si la imagen falla o contiene localhost, no enviar imagen
                if not image_url or 'localhost' in str(image_url):
                    if 'localhost' in str(image_url):
                        print(
                            "No se puede enviar imagen con URL localhost, enviando solo texto")
                    else:
                        print(
                            "No se pudo generar la imagen del reporte, enviando solo texto")
                    image_url = None

                # Crear mensaje según disponibilidad de imagen
                if image_url:
                    # Mensaje corto cuando hay imagen válida
                    message_text = f"📊 Corte {dia_nombre} - Sin datos"
                else:
                    # Mensaje descriptivo cuando no hay imagen
                    message_text = f"📊 Tada Ecuador Pedidos {dia_nombre} - Sin datos disponibles"

                    # Agregar nota sobre imagen basada en la URL ya generada
                    if 'localhost' in str(image_url or ''):
                        message_text += "\n\n⚠️ Imagen no disponible en entorno local."
                    else:
                        message_text += "\n\n⚠️ Imagen falló en generar, revisa la configuración del sistema."
            else:
                # Obtener semanas únicas de manera eficiente
                weeks = set()
                variaciones = []

                for row in result:
                    weeks.update(row["semanas"].keys())
                    if row['variacion'] is not None:
                        variaciones.append(abs(row['variacion']))

                weeks = sorted(int(k) for k in weeks)
                max_variacion = max(variaciones) if variaciones else 1

                # Encontrar la última hora con datos en una sola iteración reversa
                ultima_semana_str = str(max(weeks)) if weeks else None
                total_ordenes_ultima_hora = 0
                ultima_hora_hoy = None

                if ultima_semana_str:
                    for row in reversed(result):
                        if ultima_semana_str in row['semanas'] and row['semanas'][ultima_semana_str] > 0:
                            if total_ordenes_ultima_hora == 0:  # Primera vez que encontramos datos
                                total_ordenes_ultima_hora = row['semanas'][ultima_semana_str]
                                ultima_hora_hoy = row['hora']
                            break

                # Preparar data para el template
                whatsapp_data = {
                    'data': result,
                    'weeks': weeks,
                    'max_variacion': max_variacion,
                    'dia_nombre': dia_nombre,
                    'total_ordenes_ultima_hora': total_ordenes_ultima_hora,
                    'daily_variation': daily_variation,
                    'daily_meta_vs_real': daily_meta_vs_real,
                    'current_time': current_time
                }

                # Generar imagen desde el template HTML
                image_url = html_to_image_service.generate_image_from_template(
                    template_path='email/hourly_variation.html',
                    context_data=whatsapp_data
                )

                print(image_url)

                # Si la imagen falla o contiene localhost, no enviar imagen
                if not image_url or 'localhost' in str(image_url):
                    if 'localhost' in str(image_url):
                        print(
                            "No se puede enviar imagen con URL localhost, enviando solo texto")
                    else:
                        print(
                            "No se pudo generar la imagen del reporte, enviando solo texto")
                    image_url = None

                # Crear mensaje según disponibilidad de imagen
                # if image_url:
                if False:
                    # Mensaje corto cuando hay imagen válida
                    message_text = f"📊 Corte {dia_nombre}"
                    if ultima_hora_hoy:
                        message_text += f" - {ultima_hora_hoy}"
                else:
                    # Mensaje descriptivo cuando no hay imagen
                    message_text = f"📊 Corte {dia_nombre}"
                    if ultima_hora_hoy:
                        message_text += f" - {ultima_hora_hoy}"

                    # Agregar información resumida en el texto
                    if current_time:
                        variacion_emoji = "📈" if current_time.get(
                            'variacion', 0) >= 0 else "📉"
                        message_text += f"\n\n{variacion_emoji} Variación: {current_time.get('variacion', 0)}%"
                        message_text += f"\nActual: {current_time.get('w_actual', 0)} | Anterior: {current_time.get('w_pasada', 0)}"

                    if daily_meta_vs_real and daily_meta_vs_real.get('has_meta'):
                        cumplimiento_emoji = "✅" if daily_meta_vs_real.get(
                            'achievement_percentage', 0) >= 0 else "⚠️"
                        message_text += f"\n\n{cumplimiento_emoji} Meta: {daily_meta_vs_real.get('achievement_percentage', 0)}%"
                        message_text += f"\nReal: {daily_meta_vs_real.get('real_count', 0)} | Meta: {daily_meta_vs_real.get('meta_count', 0)}"

                    # Agregar nota sobre imagen basada en la URL ya generada
                    # if 'localhost' in str(image_url or ''):
                    #     message_text += "\n\n⚠️ Imagen no disponible."
                    # else:
                    #     message_text += "\n\n⚠️ Imagen falló en generar."

            # Obtener números de teléfono para envío
            phone_numbers = EmailNotification.get_numbers_by_type_constant(
                notification_type_constant=EmailNotificationType.TRAFFIC_REPORT
            )
            phone_numbers = list(phone_numbers)

            # Si no hay números configurados, usar número por defecto
            if not phone_numbers:
                phone_numbers = ['+593994504722']
                print(
                    "No hay números de teléfono configurados, usando número por defecto: +593994504722")

                # Modificar el mensaje para indicar que no hay números registrados
                # message_text = f"⚠️ ALERTA: No hay números registrados para reportes\n\n{message_text}"

            # print(f'Enviando reporte por WhatsApp a: {phone_numbers}')

            # print(message_text)

            # Enviar mensaje a cada número
            for phone_number in phone_numbers:
                try:
                    # Enviar mensaje con imagen solo si está disponible y no es localhost
                    response_data, response = whatsapp_service.send_message(
                        to=phone_number,
                        text=message_text,
                        image=image_url  # Será None si falló o es localhost
                    )

                    if response.status_code == 200:
                        print(f"Reporte enviado exitosamente a {phone_number}")
                    else:
                        print(
                            f"Error al enviar reporte a {phone_number}: {response_data}")

                except Exception as e:
                    print(f"Error al enviar WhatsApp a {phone_number}: {e}")

        except Exception as e:
            print(f"Error al enviar el reporte por WhatsApp: {e}")
        # No se realiza limpieza automática - las imágenes permanecen en S3

    def _get_daily_meta_vs_real_optimized(self, date, hourly_data, target_week, dia, start_hour, end_hour):
        """
        Versión optimizada de get_daily_meta_vs_real que usa datos ya procesados.
        Evita consultas recursivas y duplicadas.

        Usa la misma lógica de acumulación que daily_variation para horarios que cruzan medianoche.

        Args:
            date (datetime.date): Fecha para la cual obtener la comparación
            hourly_data (list): Datos por hora ya procesados
            target_week (int): Semana objetivo
            dia (int): Día de la semana (1=Lunes, 7=Domingo)
            start_hour (int): Hora de inicio del rango de operación
            end_hour (int): Hora de fin del rango de operación

        Returns:
            dict: Diccionario con la comparación meta vs real
        """
        # Obtener la meta para la fecha
        try:
            daily_meta = DailyMeta.objects.get(date=date)
        except DailyMeta.DoesNotExist:
            return {
                'date': date,
                'has_meta': False,
                'meta_info': None,
                'real_count': 0,
                'meta_count': 0,
                'achievement_percentage': 0,
                'difference': 0,
                'status': 'no_meta',
                'meta_id': None
            }

        # Obtener el último registro del día (tráfico acumulado) usando la misma lógica que daily_variation
        real_count = 0
        last_hour_with_data = None
        week_str = str(target_week)

        # Crear lista de horas válidas según los horarios de operación
        valid_operating_hours = []
        if start_hour <= end_hour:
            # Rango normal (ej: 12:00 a 23:00)
            valid_operating_hours = list(range(start_hour, end_hour + 1))
        else:
            # Rango que cruza medianoche (ej: 09:00 a 01:00 del día siguiente)
            valid_operating_hours = list(
                range(start_hour, 24)) + list(range(0, end_hour + 1))

        # Filtrar horas que están dentro del horario de operación y tienen datos
        hours_with_data = []
        for hour_data in hourly_data:
            if week_str in hour_data['semanas'] and hour_data['semanas'][week_str] > 0:
                hour_int = int(hour_data['hora'].split(':')[0])
                # Solo incluir horas que están dentro del horario de operación
                if hour_int in valid_operating_hours:
                    hours_with_data.append((hour_int, hour_data))

        # Ordenar por hora (considerando el cruce de medianoche)
        def sort_hour_key(item):
            hour = item[0]
            if start_hour > end_hour:  # Si cruza medianoche
                if 0 <= hour <= end_hour:  # Horas de madrugada (más tardías)
                    return hour + 24
                else:  # Horas normales del día
                    return hour
            else:
                return hour

        hours_with_data.sort(key=sort_hour_key, reverse=True)

        # Buscar el último registro del día para la meta
        for hour_int, hour_data in hours_with_data:
            count = hour_data['semanas'].get(week_str, 0)
            if count > 0:
                last_hour_with_data = hour_data['hora']

                # Si la última hora es de madrugada y cruza medianoche, calcular total acumulado
                if start_hour > end_hour and 0 <= hour_int <= end_hour:
                    real_count = self._calculate_total_with_dawn_hours(
                        hourly_data, week_str, hour_int
                    )
                else:
                    real_count = count
                break

        # Calcular porcentaje de cumplimiento como cuánto falta para llegar a la meta (negativo si falta, positivo si supera)
        meta_count = daily_meta.target_count
        achievement_percentage = 0
        if meta_count > 0:
            # Fórmula: (real - meta) / meta * 100
            # Si real < meta: resultado negativo (falta)
            # Si real = meta: resultado 0 (cumplido exacto)
            # Si real > meta: resultado positivo (superado)
            achievement_percentage = round(
                ((real_count - meta_count) / meta_count) * 100, 2)
        # Calcular diferencia
        difference = real_count - meta_count

        # Determinar el estado
        if real_count >= meta_count:
            status = 'achieved'
        elif real_count >= meta_count * 0.8:  # 80% o más
            status = 'close'
        else:
            status = 'behind'

        return {
            'date': date.strftime('%Y-%m-%d') if date else None,
            'has_meta': True,
            'real_count': real_count,
            'meta_count': meta_count,
            'achievement_percentage': achievement_percentage,
            'difference': difference,
            'status': status,
            'last_hour_with_data': last_hour_with_data,
            'meta_id': daily_meta.id
        }

    def _calculate_total_with_dawn_hours(self, hourly_data, week_str, last_dawn_hour):
        """
        Calcula el total del día cuando la última hora registrada es de madrugada (00:00 a 03:00).

        La lógica es simple: 
        1. Encontrar el valor a las 00:00 (si existe)
        2. Encontrar el último valor de madrugada (01:00, 02:00 o 03:00)
        3. Sumar: valor_00:00 + último_valor_madrugada

        Ejemplo: 00:00 = 722, 01:00 = 18 → Total = 722 + 18 = 740

        Args:
            hourly_data (list): Datos por hora procesados
            week_str (str): Semana como string
            last_dawn_hour (int): Última hora de madrugada registrada (0-3)

        Returns:
            int: Total acumulado del día
        """
        value_at_midnight = 0  # Valor a las 00:00
        # Último valor de madrugada (01:00, 02:00, 03:00)
        last_dawn_value = 0

        # Buscar el valor a las 00:00
        for hour_data in hourly_data:
            hour_int = int(hour_data['hora'].split(':')[0])
            if hour_int == 0:  # 00:00
                count = hour_data['semanas'].get(week_str, 0)
                if count > 0:
                    value_at_midnight = count
                break

        # Buscar el último valor de madrugada (01:00, 02:00, 03:00)
        # Solo considerar horas de 1 a 3 AM
        if last_dawn_hour > 0:  # Solo si la última hora es mayor a 00:00
            dawn_values = {}
            for hour_data in hourly_data:
                hour_int = int(hour_data['hora'].split(':')[0])
                if 1 <= hour_int <= last_dawn_hour:  # 01:00 a 03:00
                    count = hour_data['semanas'].get(week_str, 0)
                    if count > 0:
                        dawn_values[hour_int] = count

            # Obtener el último valor de madrugada (hora más tardía)
            if dawn_values:
                max_dawn_hour_key = max(dawn_values.keys())
                last_dawn_value = dawn_values[max_dawn_hour_key]

        # Calcular total: valor de medianoche + último valor de madrugada
        total = value_at_midnight + last_dawn_value

        # Si no hay valor a las 00:00 pero sí hay valores de madrugada,
        # usar solo el último valor de madrugada
        if value_at_midnight == 0 and last_dawn_value > 0:
            total = last_dawn_value

        # Si no hay valores de madrugada pero sí a las 00:00,
        # usar solo el valor de medianoche
        if last_dawn_value == 0 and value_at_midnight > 0:
            total = value_at_midnight

        return total
