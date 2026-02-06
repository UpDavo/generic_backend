from django.db import models
from core.models import BaseModel


class YearlySalesData(BaseModel):
    """
    Modelo para carga masiva de datos de ventas por fecha y ciudad.
    Se usa cuando no hay datos en SalesRecord para ciertos períodos.
    """
    
    REPORT_TYPE_CHOICES = [
        ('hectolitros', 'Hectolitros'),
        ('caja', 'Caja'),
    ]
    
    date = models.DateField(
        verbose_name='Fecha',
        help_text='Fecha del registro de venta'
    )
    
    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Ciudad',
        help_text='Ciudad específica. Si es NULL, representa el total general'
    )
    
    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Total',
        help_text='Valor total de ventas (hectolitros o cajas según report_type)'
    )
    
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPE_CHOICES,
        verbose_name='Tipo de Reporte',
        help_text='Tipo de dato: hectolitros o caja',
        default='hectolitros'
    )
    
    class Meta:
        verbose_name = 'Dato de Venta Anual'
        verbose_name_plural = 'Datos de Ventas Anuales'
        ordering = ['-date', 'city']
        indexes = [
            models.Index(fields=['date', 'city', 'report_type']),
            models.Index(fields=['date', 'report_type']),
        ]
    
    def __str__(self):
        city_str = self.city if self.city else 'Total General'
        return f'{self.date} - {city_str} - {self.total} ({self.report_type})'
