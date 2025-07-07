from django.core.management.base import BaseCommand
from core.models import EmailNotificationType


class Command(BaseCommand):
    help = 'Poblar los tipos de notificación por email'

    def handle(self, *args, **options):
        EmailNotificationType.populate()
        self.stdout.write(
            self.style.SUCCESS('Tipos de notificación poblados exitosamente.')
        )
