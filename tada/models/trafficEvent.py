from django.db import models
from core.models import BaseModel
from tada.utils.constants import APPS


class TrafficEvent(BaseModel):
    braze_id = models.CharField(max_length=100, default='default_event')
    name = models.CharField(max_length=100, default='Default Event')

    def __str__(self):
        return f"Traffic event: {self.name}"
