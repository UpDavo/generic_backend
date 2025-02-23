from django.db import models
from core.models import BaseModel
from django.utils import timezone


class Price(BaseModel):
    month = models.DateField()
    value = models.FloatField()

    @classmethod
    def create_price_for_current_month(cls, value):
        """
        Crea un precio para el mes actual si no existe.
        """
        first_day_of_month = timezone.now().replace(day=1).date()

        # Verificar si ya existe un precio para el mes
        if not cls.objects.filter(month=first_day_of_month).exists():
            return cls.objects.create(month=first_day_of_month, value=value)
        else:
            print("Ya existe un precio para este mes.")
            return None
