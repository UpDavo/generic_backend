from django.db import models
from core.models import BaseModel


class NotificationMessage(BaseModel):
    notification_type = models.CharField(max_length=50, unique=True)
    message = models.TextField()

    def __str__(self):
        return f"{self.type}: {self.message}"
