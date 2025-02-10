from django.db import models
from authentication.models.permission import Permission
from core.models import BaseModel
from django.apps import apps


class Role(BaseModel):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    permissions = models.ManyToManyField(Permission, related_name="roles")
    is_admin = models.BooleanField(default=False)

    def get_permissions(self):
        return self.permissions.all()

    def __str__(self):
        return self.name
