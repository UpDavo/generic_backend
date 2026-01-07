from django.db import models
from core.models import BaseModel


class SKU(BaseModel):
    """
    Model to store product SKUs.
    
    A SKU can be of type:
    - principal: Individual/simple SKU
    - combo: SKU composed of other child SKUs
    """
    
    TYPE_CHOICES = [
        ('principal', 'Principal'),
        ('combo', 'Combo'),
    ]
    
    type = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='principal',
        help_text='SKU type: principal or combo'
    )
    vendor_code = models.CharField(
        max_length=100,
        help_text='Vendor code'
    )
    sku_vtex = models.CharField(
        max_length=100,
        unique=True,
        help_text='VTEX SKU (unique)'
    )
    name = models.CharField(
        max_length=255,
        help_text='Product name'
    )
    units = models.IntegerField(
        default=1,
        help_text='Number of units'
    )
    milliliters_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text='Milliliters per unit'
    )
    units_per_box = models.IntegerField(
        null=True,
        blank=True,
        help_text='Number of units per box'
    )
    hectoliters_per_unit = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Hectoliters per unit'
    )
    hectoliters_per_box = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        help_text='Hectoliters per box'
    )
    homologated_names = models.JSONField(
        default=list,
        blank=True,
        help_text='List of alternative/homologated names for matching purposes'
    )
    
    # Relationship for combos: a combo can have multiple child SKUs
    child_skus = models.ManyToManyField(
        'self',
        symmetrical=False,
        blank=True,
        related_name='parent_skus',
        help_text='Child SKUs that compose this combo (only applies if type=combo)'
    )
    
    class Meta:
        db_table = 'tada_sku'
        verbose_name = 'SKU'
        verbose_name_plural = 'SKUs'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.sku_vtex} - {self.name}"
    
    def clean(self):
        """
        Custom validation to ensure only combos have children.
        """
        from django.core.exceptions import ValidationError
        
        # This validation will run after the object is saved
        # due to ManyToMany relationships
        if self.type == 'principal' and self.child_skus.exists():
            raise ValidationError(
                'A "principal" type SKU cannot have child SKUs. '
                'Change the type to "combo" or remove the child SKUs.'
            )
    
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
        """Check if the given name matches the SKU name or any homologated name."""
        if not name:
            return False
        
        name_lower = name.lower().strip()
        
        # Check main name
        if self.name.lower().strip() == name_lower:
            return True
        
        # Check homologated names
        return any(h.lower().strip() == name_lower for h in self.homologated_names)
