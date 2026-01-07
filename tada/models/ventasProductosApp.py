from django.db import models
from core.models import BaseModel
from .ventasProductosCompra import VentasProductosCompra


class VentasProductosAppMaterial(BaseModel):
    """
    Intermediate model for the many-to-many relationship between 
    VentasProductosApp and VentasProductosCompra with quantity.
    """
    ventas_productos_app = models.ForeignKey(
        'VentasProductosApp',
        on_delete=models.CASCADE,
        related_name='material_items'
    )
    ventas_productos_compra = models.ForeignKey(
        VentasProductosCompra,
        on_delete=models.CASCADE,
        related_name='used_in_apps'
    )
    quantity = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text='Quantity of this material used'
    )

    class Meta:
        db_table = 'tada_ventas_productos_app_material'
        verbose_name = 'Ventas Productos App Material'
        verbose_name_plural = 'Ventas Productos App Materials'
        unique_together = ('ventas_productos_app', 'ventas_productos_compra')

    def __str__(self):
        return f"{self.ventas_productos_app.code} - {self.ventas_productos_compra.code} (qty: {self.quantity})"


class VentasProductosApp(BaseModel):
    """
    Model to store app products (sales products).

    A product can be of type:
    - principal: Individual/simple product
    - combo: Product composed of other materials
    """

    TYPE_CHOICES = [
        ('principal', 'Principal'),
        ('combo', 'Combo'),
    ]

    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='principal',
        help_text='Product type: principal or combo'
    )
    code = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique product SKU code'
    )
    name = models.CharField(
        max_length=255,
        help_text='Product name'
    )
    unit = models.IntegerField(
        default=1,
        help_text='Quantity/units'
    )

    # Many-to-many relationship with VentasProductosCompra through intermediate model
    materials = models.ManyToManyField(
        VentasProductosCompra,
        through=VentasProductosAppMaterial,
        related_name='app_products',
        blank=True,
        help_text='Materials that compose this product'
    )

    class Meta:
        db_table = 'tada_ventas_productos_app'
        verbose_name = 'Ventas Producto App'
        verbose_name_plural = 'Ventas Productos App'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.code} - {self.name}"

    def clean(self):
        """
        Custom validation to ensure combos have materials.
        """
        from django.core.exceptions import ValidationError

        # This validation will run after the object is saved
        # due to ManyToMany relationships
        if self.type == 'combo' and self.pk and not self.materials.exists():
            raise ValidationError(
                'A "combo" type product should have at least one material.'
            )

    def add_material(self, material, quantity):
        """Add a material with quantity to this product."""
        VentasProductosAppMaterial.objects.update_or_create(
            ventas_productos_app=self,
            ventas_productos_compra=material,
            defaults={'quantity': quantity}
        )

    def remove_material(self, material):
        """Remove a material from this product."""
        VentasProductosAppMaterial.objects.filter(
            ventas_productos_app=self,
            ventas_productos_compra=material
        ).delete()

    def get_materials_with_quantities(self):
        """Get all materials with their quantities as a dictionary."""
        return {
            item.ventas_productos_compra: item.quantity
            for item in self.material_items.select_related('ventas_productos_compra').all()
        }
