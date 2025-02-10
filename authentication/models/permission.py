from django.db import models
from authentication.models import HttpMethod
from core.models import BaseModel


class Permission(BaseModel):
    name = models.CharField(max_length=100)
    path = models.CharField(max_length=100)
    methods = models.ManyToManyField(HttpMethod, related_name="permissions")
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.path})"
