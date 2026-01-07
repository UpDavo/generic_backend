from django.db import models
from core.models import BaseModel


class POC(BaseModel):
    """
    Model to store Points of Contact (POC) information.
    
    A POC represents a point of sale or contact location with geographical
    and identification information.
    """
    
    REGION_CHOICES = [
        ('costa', 'Costa'),
        ('sierra', 'Sierra'),
        ('oriente', 'Oriente'),
        ('insular', 'Insular'),
    ]
    
    id_poc = models.CharField(
        max_length=100,
        unique=True,
        help_text='Unique POC identifier'
    )
    city = models.CharField(
        max_length=100,
        help_text='City in Ecuador'
    )
    name = models.CharField(
        max_length=255,
        help_text='POC name'
    )
    region = models.CharField(
        max_length=20,
        choices=REGION_CHOICES,
        help_text='Region: Costa, Sierra, Oriente, or Insular'
    )
    homologated_names = models.JSONField(
        default=list,
        blank=True,
        help_text='List of alternative/homologated names for matching purposes'
    )
    
    class Meta:
        db_table = 'tada_poc'
        verbose_name = 'POC'
        verbose_name_plural = 'POCs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['id_poc']),
            models.Index(fields=['city']),
            models.Index(fields=['region']),
        ]
    
    def __str__(self):
        return f"{self.id_poc} - {self.name}"
    
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
        """Check if the given name matches the POC name or any homologated name."""
        if not name:
            return False
        
        name_lower = name.lower().strip()
        
        # Check main name
        if self.name.lower().strip() == name_lower:
            return True
        
        # Check homologated names
        return any(h.lower().strip() == name_lower for h in self.homologated_names)
