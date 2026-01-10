from decimal import Decimal
from django.db import models
from django.utils.timezone import now
from django.core.validators import MinValueValidator
from core.models import BaseModel
from tada.utils.constants import APPS


class HectolitresDailyMeta(BaseModel):
    """
    Meta diaria de hectolitros para ventas.
    Similar a DailyMeta pero específica para el objetivo de hectolitros.
    """
    date = models.DateField(
        unique=True, 
        help_text="Fecha para la cual se establece la meta de hectolitros"
    )
    target_hectolitres = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0'))],
        help_text="Meta de hectolitros esperada para el día"
    )
    app = models.CharField(max_length=50, default=APPS['SALES'])

    class Meta:
        ordering = ['-date']
        verbose_name = "Meta Diaria de Hectolitros"
        verbose_name_plural = "Metas Diarias de Hectolitros"

    def __str__(self):
        return f"Meta Hectolitros {self.date}: {self.target_hectolitres} HL"

    @staticmethod
    def get_work_hours_range():
        """Rango de horas laborales (por compatibilidad)"""
        return (7, 3)
