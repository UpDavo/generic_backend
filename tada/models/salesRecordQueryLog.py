from django.db import models
from core.models import BaseModel
from authentication.models import CustomUser
from tada.utils.constants import APPS


class SalesRecordQueryLog(BaseModel):
    """
    Log para registrar cada consulta al histórico de ventas (SalesRecord).
    Similar a SalesReportLog pero para consultas de histórico.
    
    Se crea cada vez que:
    - Se lista el histórico (SalesRecordHistoryListView)
    - Se descarga el histórico (SalesRecordHistoryDownloadView)
    """
    query_type = models.CharField(
        max_length=50,
        choices=[
            ('list', 'Lista/Consulta'),
            ('download', 'Descarga Excel')
        ],
        help_text="Tipo de consulta realizada"
    )
    records_returned = models.IntegerField(
        default=0,
        help_text="Cantidad de registros SalesRecord devueltos en la consulta"
    )
    filters_applied = models.JSONField(
        null=True,
        blank=True,
        help_text="Filtros aplicados en la consulta (start_date, end_date, poc_name, etc.)"
    )
    date = models.DateField(help_text="Fecha de la consulta")
    time = models.TimeField(help_text="Hora de la consulta")
    app = models.CharField(
        max_length=50,
        default=APPS['SALES_CHECK'],
        help_text="App asociada (SALES_CHECK)"
    )
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_query_logs',
        help_text="Usuario que realizó la consulta"
    )
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['-date', '-time']),
            models.Index(fields=['app']),
            models.Index(fields=['user']),
            models.Index(fields=['query_type']),
        ]

    def __str__(self):
        return f"Sales Query Log {self.id} - {self.query_type} ({self.records_returned} records)"
