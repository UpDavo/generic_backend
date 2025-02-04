from django.db import models
from django.conf import settings


class ActiveSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='active_sessions'
    )
    # Ajusta si quieres mayor longitud
    access_token = models.CharField(max_length=512, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"ActiveSession(user={self.user}, token={self.access_token[:10]}...)"
