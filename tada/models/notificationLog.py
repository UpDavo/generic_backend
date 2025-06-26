from django.db import models
from authentication.models import CustomUser
from django.utils.timezone import now
from core.models import BaseModel


class NotificationLog(BaseModel):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    email = models.EmailField()
    notification_type = models.CharField(max_length=50)
    title = models.CharField(max_length=50, default='')
    message = models.TextField()
    sent_at = models.DateTimeField(default=now)

    def __str__(self):
        return f"{self.user.username} sent {self.notification_type} to {self.email} at {self.sent_at}"
