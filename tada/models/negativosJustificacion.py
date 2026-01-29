from django.db import models
from core.models import BaseModel


class NegativosJustificacion(BaseModel):
    """
    Model to store negative case justifications from customer service agents.
    Used to analyze negative tickets vs justified cases.
    """

    id_ticket = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique ticket identifier'
    )
    titulo_caso = models.CharField(
        max_length=500,
        help_text='Case title'
    )
    created_by = models.ForeignKey(
        'authentication.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='negativos_justificaciones_creadas',
        help_text='User who created this justification'
    )
    hora_inicio = models.DateTimeField(
        help_text='Case start time'
    )
    hora_fin = models.DateTimeField(
        help_text='Case end time'
    )
    justificacion = models.TextField(
        help_text='Justification text for the negative case'
    )
    es_tienda = models.BooleanField(
        default=False,
        help_text='Whether the case is related to a store/POC'
    )
    poc = models.ForeignKey(
        'POC',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='negativos_justificaciones',
        help_text='Related POC/store if es_tienda is True'
    )

    class Meta:
        db_table = 'negativos_justificacion'
        verbose_name = 'Negativo Justificación'
        verbose_name_plural = 'Negativos Justificaciones'
        ordering = ['-hora_inicio']
        indexes = [
            models.Index(fields=['id_ticket']),
            models.Index(fields=['hora_inicio']),
            models.Index(fields=['-hora_inicio']),
        ]

    def __str__(self):
        return f"{self.id_ticket} - {self.titulo_caso}"

    @property
    def duracion_caso(self):
        """Calculate case duration in minutes."""
        if self.hora_inicio and self.hora_fin:
            delta = self.hora_fin - self.hora_inicio
            return delta.total_seconds() / 60
        return None
