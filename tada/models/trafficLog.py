from django.db import models
from django.utils.timezone import now
from core.models import BaseModel
from tada.utils.constants import APPS


class TrafficLog(BaseModel):
    event = models.ForeignKey(
        'TrafficEvent', on_delete=models.CASCADE, related_name='traffic_logs')
    date = models.DateField(default=now)
    time = models.TimeField(default=now)
    count = models.IntegerField(default=0)
    app = models.CharField(max_length=50, default=APPS['TRAFFIC'])

    def __str__(self):
        return f"Traffic log on {self.date} at {self.time}: {self.count} events"
