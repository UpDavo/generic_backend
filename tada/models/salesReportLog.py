from django.db import models
from core.models import BaseModel
from authentication.models import CustomUser


class SalesReportLog(BaseModel):
    """
    Log para registrar cada procesamiento de reporte de ventas.
    Similar a WebhookLog pero para sales reports.
    """
    filename = models.CharField(max_length=500, help_text="Nombre del archivo procesado")
    rows_processed = models.IntegerField(default=0, help_text="Cantidad de filas procesadas")
    date = models.DateField(help_text="Fecha del procesamiento")
    time = models.TimeField(help_text="Hora del procesamiento")
    app = models.CharField(max_length=50, help_text="App asociada (SALES)")
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_report_logs',
        help_text="Usuario que procesó el reporte"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-date', '-time']),
            models.Index(fields=['app']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"Sales Report Log {self.id} - {self.filename} ({self.rows_processed} rows)"
