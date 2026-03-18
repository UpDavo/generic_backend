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
    
    # Campos adicionales para edición
    edited_by = models.ForeignKey(
        'authentication.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='edited_webhooks',
        help_text="Usuario que editó el registro"
    )
    poc = models.CharField(
        max_length=200,
        blank=True,
        null=True,
        help_text="Punto de venta de origen"
    )
    comment = models.TextField(
        blank=True,
        null=True,
        help_text="Comentario sobre el webhook"
    )
    repurchased = models.BooleanField(
        default=False,
        help_text="Indica si el cliente volvió a comprar"
    )
    is_edited = models.BooleanField(
        default=False,
        help_text="Indica si el registro ya fue editado (solo se puede editar una vez)"
    )
    edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha y hora de la edición"
    )
    numero_orden = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        help_text="Número de orden relacionado al webhook"
    )

    def __str__(self):
        return f"Webhook log from {self.source or 'unknown'} on {self.date} at {self.time}"
