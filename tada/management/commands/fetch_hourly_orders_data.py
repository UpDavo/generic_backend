from django.core.management.base import BaseCommand
from tada.services.command_service import execute_fetch


class Command(BaseCommand):
    help = 'Comando para obtener datos de órdenes por hora y crear logs automáticos'

    def handle(self, *args, **options):
        execute_fetch()
