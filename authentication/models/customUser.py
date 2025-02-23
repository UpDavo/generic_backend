from django.contrib.auth.models import AbstractUser
from django.db import models
from authentication.managers import CustomUserManager
from authentication.models.role import Role


class CustomUser(AbstractUser):
    username = None  # 🔥 Elimina el campo `username` heredado de `AbstractUser`
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    active_session_token = models.CharField(
        max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)

    role = models.ForeignKey(
        Role,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def __str__(self):
        return self.email

    def get_permissions(self):
        """Devuelve todos los permisos del usuario en función de su rol."""
        if self.role:
            return self.role.get_permissions()
        return []
