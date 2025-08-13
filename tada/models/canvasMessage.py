from django.db import models
from core.models import BaseModel


class CanvasMessage(BaseModel):
    name = models.CharField(max_length=50, default='')
    braze_id = models.TextField()

    def __str__(self):
        return f"{self.name}: {self.braze_id}"
