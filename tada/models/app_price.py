from django.db import models
from core.models import BaseModel
from django.utils import timezone
from tada.models.price import Price
from tada.utils.constants import APPS


class AppPrice(BaseModel):
    app = models.CharField(max_length=50, default=APPS['PUSH'], unique=True)
    name = models.CharField(max_length=100, unique=True)
    price = models.ForeignKey(Price, on_delete=models.CASCADE)
    description = models.TextField(blank=True, null=True)
