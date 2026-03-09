from django.db import models
from core.models import BaseModel


class SpecialItemsLegacy(BaseModel):
    """
    Modelo para almacenar ítems especiales legacy con datos de ventas en
    hectolitros y cajas por fecha y nombre de producto/categoría.
    """

    fecha = models.DateField(
        help_text="Fecha del registro legacy"
    )
    nombre = models.CharField(
        max_length=255,
        help_text="Nombre del ítem/producto legacy"
    )
    hectolitros = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        help_text="Volumen en hectolitros"
    )
    cajas = models.DecimalField(
        max_digits=14,
        decimal_places=4,
        default=0,
        help_text="Cantidad en cajas"
    )

    class Meta:
        ordering = ['-fecha', 'nombre']
        verbose_name = "Ítem Especial Legacy"
        verbose_name_plural = "Ítems Especiales Legacy"

    def __str__(self):
        return f"{self.fecha} | {self.nombre} | {self.hectolitros} hl | {self.cajas} cajas"
