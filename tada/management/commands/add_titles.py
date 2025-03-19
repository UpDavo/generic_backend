from django.core.management.base import BaseCommand
from tada.models import NotificationLog, NotificationMessage


class Command(BaseCommand):
    help = "Actualiza los logs de notificación con sus títulos correspondientes."

    def handle(self, *args, **kwargs):
        logs = NotificationLog.objects.all()
        messages_dict = {
            message.notification_type: message.title
            for message in NotificationMessage.objects.all()
        }

        logs_to_update = []

        for log in logs:
            new_title = messages_dict.get(log.notification_type)
            if new_title and log.title != new_title:
                log.title = new_title
                logs_to_update.append(log)

        if logs_to_update:
            NotificationLog.objects.bulk_update(logs_to_update, ["title"])
            self.stdout.write(
                self.style.SUCCESS(
                    f"Se actualizaron {len(logs_to_update)} logs de notificación.")
            )
        else:
            self.stdout.write(self.style.WARNING(
                "No se realizaron actualizaciones."))
