from django.db import models
from core.models import BaseModel


class ManualYearlyData(BaseModel):
    """
    Modelo para almacenar datos históricos ingresados manualmente.
    Se usa cuando no hay datos reales para ciertos períodos (años/semanas).
    """
    
    REPORT_TYPE_CHOICES = [
        ('hectolitros', 'Hectolitros'),
        ('caja', 'Caja'),
    ]
    
    year = models.IntegerField(
        verbose_name='Año',
        help_text='Año del dato histórico'
    )
    
    start_week = models.IntegerField(
        verbose_name='Semana Inicial',
        help_text='Semana inicial del rango (1-53)'
    )
    
    end_week = models.IntegerField(
        verbose_name='Semana Final',
        help_text='Semana final del rango (1-53)'
    )
    
    report_type = models.CharField(
        max_length=20,
        choices=REPORT_TYPE_CHOICES,
        verbose_name='Tipo de Reporte',
        help_text='Tipo de dato: hectolitros o caja'
    )
    
    city = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Ciudad',
        help_text='Ciudad específica. Si es NULL, representa el total general'
    )
    
    value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Valor',
        help_text='Valor del dato histórico'
    )
    
    class Meta:
        db_table = 'manual_yearly_data'
        verbose_name = 'Dato Anual Manual'
        verbose_name_plural = 'Datos Anuales Manuales'
        ordering = ['-year', 'start_week']
        # Evitar duplicados: mismo año, semanas, tipo de reporte y ciudad
        unique_together = [['year', 'start_week', 'end_week', 'report_type', 'city']]
        indexes = [
            models.Index(fields=['year', 'start_week', 'end_week']),
            models.Index(fields=['report_type']),
            models.Index(fields=['city']),
        ]
    
    def __str__(self):
        city_str = f" - {self.city}" if self.city else " (Total)"
        return f"{self.year} W{self.start_week}-W{self.end_week} {self.report_type}{city_str}: {self.value}"
    
    def clean(self):
        from django.core.exceptions import ValidationError
        
        # Validar rangos de semanas
        if self.start_week < 1 or self.start_week > 53:
            raise ValidationError({'start_week': 'La semana inicial debe estar entre 1 y 53'})
        
        if self.end_week < 1 or self.end_week > 53:
            raise ValidationError({'end_week': 'La semana final debe estar entre 1 y 53'})
        
        if self.start_week > self.end_week:
            raise ValidationError({'start_week': 'La semana inicial no puede ser mayor que la final'})
        
        # Validar valor no negativo
        if self.value < 0:
            raise ValidationError({'value': 'El valor no puede ser negativo'})
