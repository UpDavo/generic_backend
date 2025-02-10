from django.core.management.base import BaseCommand
from authentication.models import HttpMethod


class Command(BaseCommand):
    help = "Pre-carga los métodos HTTP en la base de datos"

    def handle(self, *args, **kwargs):
        HttpMethod.preload_methods()
        self.stdout.write(self.style.SUCCESS(
            "Métodos HTTP pre-cargados exitosamente."))
