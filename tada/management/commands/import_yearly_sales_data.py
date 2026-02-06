import os
import pandas as pd
from datetime import datetime
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.conf import settings
from django.db import transaction
from tada.models import YearlySalesData


class Command(BaseCommand):
    help = 'Comando para importar datos de ventas anuales desde analysis/historico_ventas.xlsx'

    def add_arguments(self, parser):
        parser.add_argument(
            '--report-type',
            type=str,
            default='hectolitros',
            choices=['hectolitros', 'caja'],
            help='Tipo de reporte: hectolitros o caja (por defecto: hectolitros)'
        )

    def handle(self, *args, **options):
        # Archivo hardcodeado
        file_path = os.path.join(settings.BASE_DIR, 'analysis', 'historico_ventas.xlsx')
        report_type = options['report_type']
        batch_size = 500
        clear_existing = True  # Siempre eliminar datos existentes
        with_totals = True  # Siempre calcular totales

        # Validar que el archivo existe
        if not os.path.exists(file_path):
            self.stdout.write(
                self.style.ERROR(
                    f'El archivo {file_path} no existe.\n'
                    f'Asegúrate de que analysis/historico_ventas.xlsx existe en el proyecto.'
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                f'Archivo: analysis/historico_ventas.xlsx\n'
                f'Tipo de reporte: {report_type}\n'
                f'Eliminando datos existentes y cargando nuevos datos...'
            )
        )

        try:
            # Leer Excel con pandas
            df = pd.read_excel(file_path)
            
            # Validar que tiene la columna 'date'
            if 'date' not in df.columns:
                self.stdout.write(
                    self.style.ERROR('El archivo debe tener una columna "date"')
                )
                return

            # Obtener las columnas de ciudades (todas excepto 'date')
            city_columns = [col for col in df.columns if col != 'date']
            
            if not city_columns:
                self.stdout.write(
                    self.style.ERROR('No se encontraron columnas de ciudades en el archivo')
                )
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f'Ciudades detectadas: {", ".join(city_columns)}\n'
                    f'Total de filas: {len(df)}'
                )
            )

            # Eliminar todos los registros existentes del mismo tipo
            existing_count = YearlySalesData.objects.filter(
                deleted_at__isnull=True,
                report_type=report_type
            ).count()
            
            if existing_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f'Eliminando {existing_count} registros existentes de tipo "{report_type}"...'
                    )
                )
                YearlySalesData.objects.filter(
                    deleted_at__isnull=True,
                    report_type=report_type
                ).update(deleted_at=datetime.now())

            # Procesar datos
            records_to_create = []
            total_processed = 0
            errors = 0

            with transaction.atomic():
                for index, row in df.iterrows():
                    try:
                        # Parsear fecha
                        if pd.isna(row['date']):
                            self.stdout.write(
                                self.style.WARNING(f'Fila {index + 2}: Fecha vacía, omitiendo...')
                            )
                            errors += 1
                            continue

                        # Convertir fecha a formato correcto
                        if isinstance(row['date'], str):
                            # Intentar parsear la fecha desde string
                            try:
                                date_obj = pd.to_datetime(row['date'], format='%d/%m/%y').date()
                            except:
                                try:
                                    date_obj = pd.to_datetime(row['date']).date()
                                except:
                                    self.stdout.write(
                                        self.style.WARNING(
                                            f'Fila {index + 2}: No se pudo parsear la fecha "{row["date"]}"'
                                        )
                                    )
                                    errors += 1
                                    continue
                        else:
                            date_obj = pd.to_datetime(row['date']).date()

                        # Calcular el total general si se solicita
                        row_total = Decimal('0')

                        # Crear registros por cada ciudad
                        for city in city_columns:
                            value = row[city]
                            
                            # Saltar valores nulos o vacíos
                            if pd.isna(value):
                                continue

                            # Convertir a Decimal
                            try:
                                decimal_value = Decimal(str(value))
                                
                                # Saltar valores cero o negativos
                                if decimal_value <= 0:
                                    continue

                                records_to_create.append(
                                    YearlySalesData(
                                        date=date_obj,
                                        city=city,
                                        total=decimal_value,
                                        report_type=report_type
                                    )
                                )

                                row_total += decimal_value
                                total_processed += 1

                                # Si alcanzamos el tamaño del lote, crear registros
                                if len(records_to_create) >= batch_size:
                                    YearlySalesData.objects.bulk_create(records_to_create)
                                    self.stdout.write(
                                        self.style.SUCCESS(
                                            f'Insertados {len(records_to_create)} registros...'
                                        )
                                    )
                                    records_to_create = []

                            except Exception as e:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Fila {index + 2}, Ciudad {city}: '
                                        f'Error al convertir valor "{value}": {str(e)}'
                                    )
                                )
                                errors += 1
                                continue

                        # Agregar total general si se solicita y hay datos
                        if with_totals and row_total > 0:
                            records_to_create.append(
                                YearlySalesData(
                                    date=date_obj,
                                    city=None,  # NULL para total general
                                    total=row_total,
                                    report_type=report_type
                                )
                            )

                    except Exception as e:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Error procesando fila {index + 2}: {str(e)}'
                            )
                        )
                        errors += 1
                        continue

                # Insertar registros restantes
                if records_to_create:
                    YearlySalesData.objects.bulk_create(records_to_create)
                    self.stdout.write(
                        self.style.SUCCESS(
                            f'Insertados {len(records_to_create)} registros finales...'
                        )
                    )

            # Resumen final
            self.stdout.write(
                self.style.SUCCESS(
                    f'\n{"="*60}\n'
                    f'Importación completada:\n'
                    f'  - Total de registros procesados: {total_processed}\n'
                    f'  - Errores: {errors}\n'
                    f'  - Tipo de reporte: {report_type}\n'
                    f'{"="*60}'
                )
            )

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error crítico durante la importación: {str(e)}')
            )
            import traceback
            self.stdout.write(self.style.ERROR(traceback.format_exc()))
