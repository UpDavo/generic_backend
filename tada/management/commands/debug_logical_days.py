from django.core.management.base import BaseCommand
from tada.services.command_service import debug_operating_hours


class Command(BaseCommand):
    help = 'Debug para verificar horarios de operación y días lógicos de negocio'

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.SUCCESS('Iniciando debug de horarios de operación y días lógicos...')
        )
        
        debug_operating_hours()
        
        self.stdout.write(
            self.style.SUCCESS('Debug completado.')
        )
