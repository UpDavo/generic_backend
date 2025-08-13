from django.db import models
from authentication.models import CustomUser
from django.utils.timezone import now
from core.models import BaseModel
from tada.utils.constants import APPS


class CanvasLog(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    email = models.EmailField()
    name = models.CharField(max_length=50, default='')
    sent_at = models.DateTimeField(default=now)
    app = models.CharField(max_length=50, default=APPS['CANVAS'])

    def __str__(self):
        return f"{self.user.username} sent {self.name} to {self.email} at {self.sent_at}"
