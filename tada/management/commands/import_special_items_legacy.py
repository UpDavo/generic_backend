import os
import pandas as pd
from decimal import Decimal, InvalidOperation
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_date
from django.db import transaction

from tada.models import SpecialItemsLegacy


EXCEL_FILE = 'analysis/Innovaciones_consolidado.xlsx'


class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            default=False,
            help='Eliminar todos los registros existentes antes de importar'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Simular la importación sin guardar nada en la base de datos'
        )

    def handle(self, *args, **options):
        from django.conf import settings
        file_path = os.path.join(settings.BASE_DIR, EXCEL_FILE)
        clear = options['clear']
        dry_run = options['dry_run']

        # Validar existencia del archivo
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(
                f'Archivo no encontrado: {file_path}\n'
                f'Asegúrate de que {EXCEL_FILE} existe en la raíz del proyecto.'
            ))
            return

        # Leer Excel
        try:
            df = pd.read_excel(file_path)
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'No se pudo leer el archivo: {e}'))
            return

        # Normalizar columnas
        df.columns = [col.strip().lower() for col in df.columns]

        required_columns = ['fecha', 'nombre', 'hectolitros', 'cajas']
        missing = [col for col in required_columns if col not in df.columns]
        if missing:
            self.stdout.write(
                self.style.ERROR(
                    f'Columnas faltantes: {", ".join(missing)}\n'
                    f'Se esperan: Fecha, Nombre, Hectolitros, Cajas'
                )
            )
            return

        self.stdout.write(self.style.SUCCESS(
            f'Archivo: {file_path}\n'
            f'Filas detectadas: {len(df)}\n'
            f'Dry-run: {"Sí" if dry_run else "No"}\n'
            f'Limpiar datos previos: {"Sí" if clear else "No"}'
        ))

        created_count = 0
        updated_count = 0
        errors = []

        to_update = []

        for index, row in df.iterrows():
            row_num = index + 2

            # Fecha
            fecha_value = row['fecha']
            if pd.isna(fecha_value):
                errors.append(f'Fila {row_num}: Fecha vacía')
                continue
            fecha_str = fecha_value.strftime('%Y-%m-%d') if isinstance(fecha_value, pd.Timestamp) else str(fecha_value).strip()
            fecha_obj = parse_date(fecha_str)
            if not fecha_obj:
                errors.append(f'Fila {row_num}: Fecha inválida "{fecha_str}". Use YYYY-MM-DD')
                continue

            # Nombre
            nombre_value = row['nombre']
            if pd.isna(nombre_value) or str(nombre_value).strip() == '':
                errors.append(f'Fila {row_num}: Nombre vacío')
                continue
            nombre_str = str(nombre_value).strip()

            # Hectolitros
            try:
                hectolitros_val = Decimal('0') if pd.isna(row['hectolitros']) else Decimal(str(row['hectolitros']))
            except (InvalidOperation, ValueError):
                errors.append(f'Fila {row_num}: Hectolitros debe ser un número válido')
                continue

            # Cajas
            try:
                cajas_val = Decimal('0') if pd.isna(row['cajas']) else Decimal(str(row['cajas']))
            except (InvalidOperation, ValueError):
                errors.append(f'Fila {row_num}: Cajas debe ser un número válido')
                continue

            to_update.append({
                'fecha': fecha_obj,
                'nombre': nombre_str,
                'hectolitros': hectolitros_val,
                'cajas': cajas_val,
            })

        if errors:
            self.stdout.write(self.style.WARNING(f'\n{len(errors)} errores encontrados:'))
            for err in errors:
                self.stdout.write(self.style.WARNING(f'  - {err}'))

        if not to_update:
            self.stdout.write(self.style.ERROR('\nNo hay filas válidas para importar.'))
            return

        if dry_run:
            self.stdout.write(self.style.SUCCESS(
                f'\n[DRY-RUN] Se procesarían {len(to_update)} filas (sin guardar).'
            ))
            return

        # Guardar en base de datos
        with transaction.atomic():
            if clear:
                deleted, _ = SpecialItemsLegacy.objects.all().delete()
                self.stdout.write(self.style.WARNING(f'Se eliminaron {deleted} registros existentes.'))

            for item in to_update:
                existing = SpecialItemsLegacy.objects.filter(
                    fecha=item['fecha'], nombre=item['nombre']
                ).first()

                if existing:
                    existing.hectolitros = item['hectolitros']
                    existing.cajas = item['cajas']
                    existing.is_active = True
                    existing.save(update_fields=['hectolitros', 'cajas', 'is_active'])
                    updated_count += 1
                else:
                    SpecialItemsLegacy.objects.create(**item)
                    created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nImportación completada:\n'
            f'  Creados : {created_count}\n'
            f'  Actualizados: {updated_count}\n'
            f'  Errores : {len(errors)}'
        ))
