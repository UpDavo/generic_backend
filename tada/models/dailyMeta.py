from django.db import models
from django.utils.timezone import now
from django.core.validators import MinValueValidator
from core.models import BaseModel
from tada.utils.constants import APPS


class DailyMeta(BaseModel):
    date = models.DateField(
        unique=True, help_text="Fecha para la cual se establece la meta")
    target_count = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Meta de count esperada para el día"
    )
    app = models.CharField(max_length=50, default=APPS['TRAFFIC'])

    class Meta:
        ordering = ['-date']
        verbose_name = "Meta Diaria"
        verbose_name_plural = "Metas Diarias"

    def __str__(self):
        return f"Meta {self.date}: {self.target_count} count (7 AM - 3 AM)"

    @staticmethod
    def get_work_hours_range():
        return (7, 3)
