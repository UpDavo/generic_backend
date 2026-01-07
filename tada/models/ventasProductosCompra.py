from django.db import models
from core.models import BaseModel


class VentasProductosCompra(BaseModel):
    """
    Model to store purchase products (materials).
    These are the basic materials/products used in sales.
    """

    ORIGEN_CHOICES = [
        ('importado', 'Importado'),
        ('nacional', 'Nacional'),
    ]

    code = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique product code'
    )
    name = models.CharField(
        max_length=255,
        help_text='Product name'
    )
    homologated_names = models.JSONField(
        default=list,
        blank=True,
        help_text='List of alternative/homologated names for matching purposes'
    )
    mililiters_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Milliliters per unit'
    )
    box_units = models.IntegerField(
        null=True,
        blank=True,
        help_text='Number of units per box'
    )
    primary_can = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Primary can type'
    )
    returnable = models.BooleanField(
        default=False,
        help_text='Whether the product is returnable'
    )
    origen = models.CharField(
        max_length=20,
        choices=ORIGEN_CHOICES,
        null=True,
        blank=True,
        help_text='Product origin: imported or national'
    )
    cost_per_unit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cost per unit'
    )
    cost_per_box = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cost per box'
    )
    cost_per_hectoliter = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Cost per hectoliter'
    )
    brand = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Product brand'
    )
    category = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text='Product category'
    )
    hectoliter_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Hectoliters per unit (e.g., 0.1)'
    )
    hectoliter_box = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Hectoliters per box'
    )

    class Meta:
        db_table = 'tada_ventas_productos_compra'
        verbose_name = 'Venta Producto Compra'
        verbose_name_plural = 'Ventas Productos Compra'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def add_homologated_name(self, name):
        """Add a new homologated name if it doesn't exist."""
        if name and name not in self.homologated_names:
            self.homologated_names.append(name)
            self.save()

    def remove_homologated_name(self, name):
        """Remove a homologated name if it exists."""
        if name in self.homologated_names:
            self.homologated_names.remove(name)
            self.save()

    def matches_name(self, name):
        """Check if the given name matches the product name or any homologated name."""
        if not name:
            return False

        name_lower = name.lower().strip()

        # Check main name
        if self.name.lower().strip() == name_lower:
            return True

        # Check homologated names
        return any(h.lower().strip() == name_lower for h in self.homologated_names)
