from django.db import models
from core.models import BaseModel
from django.utils import timezone
from tada.utils.constants import APPS


class Price(BaseModel):
    month = models.DateField()
    value = models.FloatField()
    app = models.CharField(max_length=50, default=APPS['PUSH'])

    @classmethod
    def create_price_for_current_month(cls, value, app=None):
        """
        Crea un precio para el mes actual y app específica si no existe.
        """
        if app is None:
            app = str(APPS['PUSH'])
            
        first_day_of_month = timezone.now().replace(day=1).date()

        # Verificar si ya existe un precio para el mes y app
        if not cls.objects.filter(month=first_day_of_month, app=app).exists():
            return cls.objects.create(month=first_day_of_month, value=value, app=app)
        else:
            print(f"Ya existe un precio para este mes y app {app}.")
            return None
    
    @classmethod
    def get_price_history_for_app(cls, app):
        """
        Obtiene el historial de precios para una app específica.
        """
        return cls.objects.filter(app=app, deleted_at__isnull=True).order_by('-month')
    
    @classmethod
    def get_latest_price_for_app(cls, app):
        """
        Obtiene el precio más reciente para una app específica.
        """
        return cls.objects.filter(app=app, deleted_at__isnull=True).order_by('-month').first()

    def __str__(self):
        return f"App {self.app} - {self.month}: ${self.value}"
