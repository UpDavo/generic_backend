from datetime import datetime, timedelta
from tada.models.trafficLog import TrafficLog
from tada.models.dailyMeta import DailyMeta
from core.utils.emailThread import EmailThread
from core.models import EmailNotification, EmailNotificationType


class ReportService:

    def get_datetime_variation(self, dia, start_week=None, end_week=None, year=None, start_hour=7, end_hour=3):
        """
        Obtiene la variación de tráfico por hora durante un rango de semanas para un día específico.

        Args:
            dia (int): Día de la semana (1=Lunes, 2=Martes, 3=Miércoles, 4=Jueves, 5=Viernes, 6=Sábado, 7=Domingo)
            start_week (int): Número de semana de inicio (opcional, default: 7 semanas antes de la actual)
            end_week (int): Número de semana de fin (opcional, default: semana actual)
            year (int): Año para el cual obtener los datos (opcional, default: año actual)
            start_hour (int): Hora de inicio del rango (opcional, default: 7 para 07:00 am)
            end_hour (int): Hora de fin del rango (opcional, default: 3 para 03:00 am)

        Returns:
            list: Lista de diccionarios con datos de tráfico por hora
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

        for log in traffic_logs:
            # Obtener la hora (sin minutos)
            hour = log.time.hour
            hour_key = f"{hour:02d}:00"

            # Obtener el día de la semana del registro (1=Lunes, 7=Domingo)
            log_weekday = log.date.isoweekday()

            # Verificar si el registro es válido para nuestro rango de tiempo
            is_valid_record = False

            if start_hour <= end_hour:
                # Rango normal: solo registros del día especificado
                if log_weekday == dia and hour in valid_hours:
                    is_valid_record = True
            else:
                # Rango que cruza medianoche
                if log_weekday == dia:
                    # Registros del día principal (desde start_hour hasta 23)
                    if hour >= start_hour:
                        is_valid_record = True
                else:
                    # Calcular el día siguiente
                    next_day = dia + 1 if dia < 7 else 1
                    if log_weekday == next_day:
                        # Registros del día siguiente (desde 0 hasta end_hour)
                        if hour <= end_hour:
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
                    # Obtener el registro más tardío de la hora (con ventana de 2 minutos)
                    hour_int = int(hour_key.split(':')[0])

                    # Filtrar registros dentro de la ventana de tiempo
                    # Considerar registros desde 2 minutos antes de la hora hasta 59 minutos después
                    valid_records = []
                    for record in weeks_data[week_num]:
                        record_hour = record['time'].hour
                        record_minute = record['time'].minute

                        # Si es la hora exacta, tomar todos los registros de esa hora
                        if record_hour == hour_int:
                            valid_records.append(record)
                        # Si es la hora anterior y los minutos son >= 58, considerar como de la siguiente hora
                        elif record_hour == hour_int - 1 and record_minute >= 58:
                            valid_records.append(record)

                    if valid_records:
                        # Obtener el registro más tardío
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
            result, start_week, end_week)

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
                            target_week=current_week
                        )
                    except Exception as e:
                        # Si hay error, solo loguear pero no fallar
                        print(
                            f"Error al obtener comparación meta vs real: {e}")
                        daily_meta_vs_real = None

        return {
            'hourly_data': result,
            'daily_variation': daily_variation,
            'daily_meta_vs_real': daily_meta_vs_real
        }

    def _calculate_daily_variation(self, hourly_data, start_week, end_week):
        """
        Calcula la variación total del día completo comparando la semana actual vs la semana anterior.

        Toma el último registro del día para cada semana independientemente:
        - Semana actual: último registro disponible (ej: 10:00 con 2)
        - Semana anterior: último registro disponible (ej: 23:00 con 394)

        Cada registro de hora es un total acumulado, no un incremento.
        Considera que el día termina a las 3 AM como máximo, después de eso ya es otro día.
        Las horas se priorizan: 3 AM > 2 AM > 1 AM > 0 AM > 23 PM > 22 PM > ... > 7 AM.

        Args:
            hourly_data (list): Datos por hora procesados
            start_week (int): Semana de inicio
            end_week (int): Semana de fin

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
        # Considerando que el máximo por día son las 3 AM
        comparison_hour = None
        current_week_total = 0
        previous_week_total = 0

        # Ordenar las horas de mayor a menor para encontrar la última hora del día
        hours_with_data = []
        for hour_data in hourly_data:
            if (current_week_str in hour_data['semanas'] and hour_data['semanas'][current_week_str] > 0) or \
               (previous_week_str in hour_data['semanas'] and hour_data['semanas'][previous_week_str] > 0):
                hour_int = int(hour_data['hora'].split(':')[0])
                hours_with_data.append((hour_int, hour_data))

        # Ordenar por hora (considerando el cruce de medianoche)
        # Las horas de 0 a 3 AM son las más tardías del día
        def sort_hour_key(item):
            hour = item[0]
            # Prioridad: 3 AM > 2 AM > 1 AM > 0 AM > 23 PM > 22 PM > ... > 7 AM
            if 0 <= hour <= 3:  # Horas de madrugada (más tardías)
                return hour + 24
            else:  # Horas normales del día
                return hour

        hours_with_data.sort(key=sort_hour_key, reverse=True)

        # Buscar el último registro del día para cada semana por separado
        # Buscar el último registro de la semana actual (último del día)
        current_week_comparison_hour = None
        for hour_int, hour_data in hours_with_data:
            current_count = hour_data['semanas'].get(current_week_str, 0)
            if current_count > 0:
                current_week_total = current_count
                current_week_comparison_hour = hour_data['hora']
                break

        # Buscar el último registro de la semana anterior (último del día)
        previous_week_comparison_hour = None
        for hour_int, hour_data in hours_with_data:
            previous_count = hour_data['semanas'].get(previous_week_str, 0)
            if previous_count > 0:
                previous_week_total = previous_count
                previous_week_comparison_hour = hour_data['hora']
                break

        # Usar la hora de la semana actual como referencia para comparación
        # (o la de la semana anterior si no hay datos en la actual)
        comparison_hour = current_week_comparison_hour or previous_week_comparison_hour

        # Calcular totales para todas las semanas (usando el último registro de cada semana)
        weekly_totals = {}
        for week in weeks:
            week_str = str(week)
            week_total = 0

            # Buscar el último registro del día que tenga datos para esta semana específica
            for hour_int, hour_data in hours_with_data:
                count = hour_data['semanas'].get(week_str, 0)
                if count > 0:
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

            # Mapear número de día a nombre (usar constante para evitar recrear el diccionario)
            dias_nombres = {
                1: "Lunes", 2: "Martes", 3: "Miércoles", 4: "Jueves",
                5: "Viernes", 6: "Sábado", 7: "Domingo"
            }
            dia_nombre = dias_nombres.get(dia_seleccionado, "Desconocido")

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
                    'daily_meta_vs_real': daily_meta_vs_real
                }

                # print(email_data)

                # Crear el subject dinámico
                subject = f"Tada Ecuador Pedidos {dia_nombre}"
                if ultima_hora_hoy:
                    subject += f" - {ultima_hora_hoy}"

            # Enviar el correo usando el nuevo método con TRAFFIC_REPORT
            EmailNotification.send_notification_by_type_constant(
                email_template='email/hourly_variation.html',
                subject=subject,
                email_data=email_data,
                notification_type_constant=EmailNotificationType.TRAFFIC_REPORT
            )

        except Exception as e:
            print(f"Error al enviar el reporte por email: {e}")

    def _get_daily_meta_vs_real_optimized(self, date, hourly_data, target_week):
        """
        Versión optimizada de get_daily_meta_vs_real que usa datos ya procesados.
        Evita consultas recursivas y duplicadas.

        Args:
            date (datetime.date): Fecha para la cual obtener la comparación
            hourly_data (list): Datos por hora ya procesados
            target_week (int): Semana objetivo

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
                'status': 'no_meta'
            }

        # Obtener el último registro del día (tráfico acumulado) usando datos ya procesados
        real_count = 0
        last_hour_with_data = None
        week_str = str(target_week)

        for hour_data in reversed(hourly_data):
            if week_str in hour_data['semanas'] and hour_data['semanas'][week_str] > 0:
                real_count = hour_data['semanas'][week_str]
                last_hour_with_data = hour_data['hora']
                break

        # Calcular porcentaje de cumplimiento
        meta_count = daily_meta.target_count
        achievement_percentage = 0
        if meta_count > 0:
            achievement_percentage = round((real_count / meta_count) * 100, 2)

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
            'last_hour_with_data': last_hour_with_data
        }
