from django.core.management.base import BaseCommand
from tada.models import SalesRecord


class Command(BaseCommand):
    help = 'Elimina todos los registros de SalesRecord de la base de datos'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirma la eliminación sin pedir confirmación interactiva',
        )

    def handle(self, *args, **options):
        total_records = SalesRecord.objects.count()
        
        if total_records == 0:
            self.stdout.write(self.style.WARNING('No hay registros de SalesRecord para eliminar.'))
            return

        self.stdout.write(self.style.WARNING(f'Se encontraron {total_records} registros de SalesRecord.'))

        if not options['confirm']:
            confirm = input('¿Estás seguro de que deseas eliminar TODOS los registros? (yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.ERROR('Operación cancelada.'))
                return

        # Eliminar todos los registros
        self.stdout.write('Eliminando registros...')
        deleted_count, _ = SalesRecord.objects.all().delete()
        
        self.stdout.write(self.style.SUCCESS(f'✓ Se eliminaron {deleted_count} registros de SalesRecord exitosamente.'))
