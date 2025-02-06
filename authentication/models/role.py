from django.db import models
from authentication.models import Permission


class Role(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    permissions = models.ManyToManyField(Permission, related_name="roles")

    def __str__(self):
        return self.name
