from django.db import models
from core.models import BaseModel
from authentication.models import CustomUser


class SalesUploadLog(BaseModel):
    """
    Log simple para registrar uploads de ventas con rango de fechas.
    """
    date_processed = models.DateTimeField(auto_now_add=True, help_text="Fecha y hora del procesamiento")
    initrowdate = models.DateField(help_text="Fecha inicial de los datos procesados")
    endrowdate = models.DateField(help_text="Fecha final de los datos procesados")
    rows_count = models.IntegerField(default=0, help_text="Cantidad total de registros procesados")
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_upload_logs',
        help_text="Usuario que procesó el reporte"
    )
    
    class Meta:
        ordering = ['-date_processed']
        indexes = [
            models.Index(fields=['-date_processed']),
            models.Index(fields=['initrowdate', 'endrowdate']),
        ]

    def __str__(self):
        return f"Sales Upload {self.date_processed} - Desde {self.initrowdate} hasta {self.endrowdate}"
