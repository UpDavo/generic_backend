import os
import pandas as pd
from datetime import datetime
from django.core.management.base import BaseCommand
from django.conf import settings
from tada.models import TrafficEvent, TrafficLog
from tada.utils.constants import APPS


class Command(BaseCommand):
    help = 'Comando para insertar datos masivos de tráfico desde acumulados.csv'

    def add_arguments(self, parser):
        parser.add_argument(
            '--event-id',
            type=int,
            default=2,
            help='ID del evento de tráfico (por defecto: 2)'
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=1000,
            help='Tamaño del lote para bulk_create (por defecto: 1000)'
        )

    def handle(self, *args, **options):
        event_id = options['event_id']
        batch_size = options['batch_size']

        try:
            # Obtener el evento de tráfico
            event = TrafficEvent.objects.get(id=event_id)

            # Ruta del archivo CSV
            csv_file_path = os.path.join(settings.BASE_DIR, 'acumulados.csv')

            if not os.path.exists(csv_file_path):
                self.stdout.write(
                    self.style.ERROR(f'El archivo {csv_file_path} no existe')
                )
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f'Iniciando procesamiento del archivo: {csv_file_path}')
            )

            # Leer CSV con pandas
            try:
                df = pd.read_csv(csv_file_path, encoding='utf-8')
            except UnicodeDecodeError:
                # Intentar con encoding latin-1 si utf-8 falla
                df = pd.read_csv(csv_file_path, encoding='latin-1')

            # Mostrar información del DataFrame
            self.stdout.write(
                self.style.SUCCESS(
                    f'Archivo cargado exitosamente: {len(df)} filas')
            )
            self.stdout.write(f'Columnas encontradas: {list(df.columns)}')

            # Limpiar nombres de columnas (remover espacios)
            df.columns = df.columns.str.strip()

            # Eliminar filas con valores vacíos en columnas críticas
            initial_count = len(df)
            df = df.dropna(subset=['Fecha', 'Hora', 'Pedidos Acumulados'])

            # Filtrar filas donde 'Pedidos Acumulados' está vacío (string vacío)
            df = df[df['Pedidos Acumulados'].astype(str).str.strip() != '']

            cleaned_count = len(df)
            skipped_count = initial_count - cleaned_count

            self.stdout.write(
                self.style.SUCCESS(
                    f'Filas válidas después de limpieza: {cleaned_count}')
            )

            if skipped_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'Filas omitidas por datos vacíos: {skipped_count}')
                )

            # Procesar datos
            traffic_logs = []
            processed_count = 0
            error_count = 0

            for index, row in df.iterrows():
                try:
                    fecha = str(row['Fecha']).strip()
                    hora = str(row['Hora']).strip()
                    pedidos_str = str(row['Pedidos Acumulados']).strip()

                    # Parsear fecha (formato M/D/YY)
                    fecha_obj = pd.to_datetime(fecha, format='%m/%d/%y').date()

                    # Parsear hora (formato HH:MM)
                    hora_obj = pd.to_datetime(hora, format='%H:%M').time()

                    # Parsear conteo
                    count = int(float(pedidos_str))

                    # Crear objeto TrafficLog
                    traffic_log = TrafficLog(
                        event=event,
                        date=fecha_obj,
                        time=hora_obj,
                        count=count,
                        app=APPS['TRAFFIC']
                    )

                    traffic_logs.append(traffic_log)
                    processed_count += 1

                    # Insertar en lotes para optimizar la performance
                    if len(traffic_logs) >= batch_size:
                        TrafficLog.objects.bulk_create(
                            traffic_logs,
                            ignore_conflicts=True
                        )
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Insertados {len(traffic_logs)} registros...')
                        )
                        traffic_logs = []

                except (ValueError, pd.errors.ParserError) as e:
                    error_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f'Error al parsear fila {index}: {dict(row)} - {str(e)}')
                    )
                    continue

            # Insertar los registros restantes
            if traffic_logs:
                TrafficLog.objects.bulk_create(
                    traffic_logs,
                    ignore_conflicts=True
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Insertados {len(traffic_logs)} registros finales...')
                )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Procesamiento completado:\n'
                    f'- Registros procesados exitosamente: {processed_count}\n'
                    f'- Registros omitidos por datos vacíos: {skipped_count}\n'
                    f'- Registros con errores de parsing: {error_count}\n'
                    f'- Total de registros insertados: {processed_count}'
                )
            )

        except TrafficEvent.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(
                    f'El evento de tráfico con ID {event_id} no existe')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error al procesar datos: {str(e)}')
            )
            raise e
