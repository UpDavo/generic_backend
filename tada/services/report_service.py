from datetime import datetime, timedelta
from tada.models.trafficLog import TrafficLog
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
            start_week = max(1, end_week - 7)

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

        return result

    def send_report_by_email(self, dia_seleccionado):
        try:
            # Generar el reporte
            result = self.get_datetime_variation(
                dia=dia_seleccionado)

            # Mapear número de día a nombre
            dias_nombres = {
                1: "Lunes",
                2: "Martes",
                3: "Miércoles",
                4: "Jueves",
                5: "Viernes",
                6: "Sábado",
                7: "Domingo"
            }
            dia_nombre = dias_nombres.get(dia_seleccionado, "Desconocido")

            # Obtener semanas únicas ordenadas
            weeks = sorted({int(k)
                            for row in result for k in row["semanas"].keys()})

            # Calcular max_variacion para evitar división por cero
            variaciones = [abs(row['variacion'])
                           for row in result if row['variacion'] is not None]
            max_variacion = max(variaciones) if variaciones else 1

            # Calcular total de órdenes de la última hora de la semana actual
            total_ordenes_ultima_hora = 0
            if result and weeks:
                ultima_semana = str(max(weeks))
                # Buscar la última hora con datos
                for row in reversed(result):
                    if ultima_semana in row['semanas'] and row['semanas'][ultima_semana] > 0:
                        total_ordenes_ultima_hora = row['semanas'][ultima_semana]
                        break

            # Obtener la última hora de hoy existente en la data
            ultima_hora_hoy = None
            if result:
                # Buscar la hora más tardía con datos en la semana actual
                ultima_semana = str(max(weeks)) if weeks else None
                for row in reversed(result):
                    if ultima_semana and ultima_semana in row['semanas'] and row['semanas'][ultima_semana] > 0:
                        ultima_hora_hoy = row['hora']
                        break

            # Preparar data para el template
            email_data = {
                'data': result,
                'weeks': weeks,
                'max_variacion': max_variacion,
                'dia_nombre': dia_nombre,
                'total_ordenes_ultima_hora': total_ordenes_ultima_hora
            }

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
