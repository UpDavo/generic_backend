from django.db import models
from authentication.models import CustomUser
from django.utils.timezone import now
from core.models import BaseModel
from tada.utils.constants import APPS


class NotificationLog(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    email = models.EmailField()
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=50, default='')
    message = models.TextField()
    sent_at = models.DateTimeField(default=now)
    app = models.CharField(max_length=50, default=APPS['PUSH'])

    def __str__(self):
        return f"{self.user.username} sent {self.notification_type} to {self.email} at {self.sent_at}"
