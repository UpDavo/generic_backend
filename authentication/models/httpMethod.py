from django.db import models
from core.models import BaseModel


class HttpMethod(BaseModel):
    HTTP_METHODS = [
        ("GET", "GET"),
        ("POST", "POST"),
        ("PUT", "PUT"),
        ("DELETE", "DELETE"),
        ("PATCH", "PATCH"),
        ("OPTIONS", "OPTIONS"),
        ("HEAD", "HEAD"),
    ]

    name = models.CharField(max_length=10, choices=HTTP_METHODS, unique=True)

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if self.name not in dict(self.HTTP_METHODS):
            raise ValueError(f"{self.name} no es un método HTTP válido.")
        super().save(*args, **kwargs)

    @classmethod
    def preload_methods(cls):
        for method in dict(cls.HTTP_METHODS):
            cls.objects.get_or_create(name=method)
