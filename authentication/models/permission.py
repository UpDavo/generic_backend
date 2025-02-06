from django.db import models
from authentication.models import HttpMethod


class Permission(models.Model):
    name = models.CharField(max_length=100, unique=True)
    path = models.CharField(max_length=100, unique=True)
    methods = models.ManyToManyField(HttpMethod)
    description = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.name
