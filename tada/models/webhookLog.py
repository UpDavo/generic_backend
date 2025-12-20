from django.db import models
from django.utils.timezone import now
from core.models import BaseModel
from tada.utils.constants import APPS


class WebhookLog(BaseModel):
    payload = models.JSONField(
        help_text="JSON payload recibido del webhook")
    source = models.CharField(
        max_length=100, 
        blank=True, 
        null=True,
        help_text="Origen o servicio que envió el webhook")
    event_type = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Tipo de evento del webhook")
    date = models.DateField(default=now)
    time = models.TimeField(default=now)
    app = models.CharField(max_length=50, default=APPS['WEBHOOK'])

    def __str__(self):
        return f"Webhook log from {self.source or 'unknown'} on {self.date} at {self.time}"
