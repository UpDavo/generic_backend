from django.contrib.auth.models import AbstractUser
from django.db import models
from authentication.managers import CustomUserManager
from authentication.models import Role


class CustomUser(AbstractUser):
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    active_session_token = models.CharField(
        max_length=255, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    role = models.ForeignKey(
        "Role", on_delete=models.SET_NULL, null=True, blank=True)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = CustomUserManager()

    def __str__(self):
        return self.email
