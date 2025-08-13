from django.db import models
from django.utils.timezone import now
from core.models import BaseModel
from tada.utils.constants import APPS


class ExecutionLog(BaseModel):
    event = models.ForeignKey(
        'TrafficEvent', on_delete=models.CASCADE, related_name='execution_logs')
    execution_type = models.CharField(max_length=50, choices=[
        ('manual', 'Manual'),
        ('automatic', 'Automatic')
    ], default='manual')
    command = models.TextField(
        blank=True, null=True, help_text="Comando de Django ejecutado para ejecuciones automáticas")
    date = models.DateField(default=now)
    time = models.TimeField(default=now)
    app = models.CharField(max_length=50, default=APPS['EXECUTION'])

    def __str__(self):
        return f"Execution log ({self.execution_type}) on {self.date} at {self.time}"
