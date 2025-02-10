from django.db import models

from core.models import BaseModel


class EmailNotificationType(BaseModel):
    SIMPLE_NOTIFICATION = 1

    TYPE_CHOICES = (
        (SIMPLE_NOTIFICATION, 'Notificación sencilla'),
    )

    notification_type = models.PositiveSmallIntegerField(
        choices=TYPE_CHOICES, unique=True)

    def __str__(self):
        return str(self.get_notification_type_display())

    @classmethod
    def populate(cls):
        for choice in cls.TYPE_CHOICES:
            cls.objects.get_or_create(notification_type=choice[0])
