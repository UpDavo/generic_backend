from django.db import models
from core.models import BaseModel
from core.utils.storage_backend import PublicUploadStorage
from authentication.models import CustomUser
import hashlib


def sales_file_upload_path(instance, filename):
    """
    Genera la ruta donde se guardará el archivo.
    Formato: sales_files/YYYY/MM/filename
    """
    from datetime import datetime
    now = datetime.now()
    return f"sales_files/{now.year}/{now.month:02d}/{filename}"


class SalesFileStorage(BaseModel):
    """
    Modelo para almacenar los archivos Excel originales de ventas.
    
    Permite:
    1. Guardar el archivo original para auditoría
    2. Comparar archivos nuevos con el anterior usando hash
    3. Identificar qué filas cambiaron entre versiones
    """
    
    # Archivo original (usando S3 público)
    file = models.FileField(
        upload_to=sales_file_upload_path,
        storage=PublicUploadStorage(),
        help_text="Archivo Excel original subido"
    )
    
    # Metadata del archivo
    filename = models.CharField(
        max_length=500,
        help_text="Nombre original del archivo"
    )
    file_size = models.BigIntegerField(
        help_text="Tamaño del archivo en bytes"
    )
    
    # Hash para comparación rápida
    file_hash = models.CharField(
        max_length=64,
        db_index=True,
        help_text="SHA-256 hash del contenido del archivo"
    )
    
    # Hash de contenido (filas de datos)
    content_hash = models.CharField(
        max_length=64,
        db_index=True,
        null=True,
        blank=True,
        help_text="SHA-256 hash del contenido de datos (sin headers)"
    )
    
    # Rango de fechas del archivo
    date_range_start = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha más antigua en el archivo"
    )
    date_range_end = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha más reciente en el archivo"
    )
    
    # Estadísticas del archivo
    total_rows = models.IntegerField(
        default=0,
        help_text="Total de filas de datos en el archivo"
    )
    unique_stores = models.IntegerField(
        default=0,
        help_text="Cantidad de tiendas únicas"
    )
    unique_skus = models.IntegerField(
        default=0,
        help_text="Cantidad de SKUs únicos"
    )
    
    # Datos de procesamiento
    processed = models.BooleanField(
        default=False,
        help_text="Si el archivo ya fue procesado"
    )
    processed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fecha/hora de procesamiento"
    )
    
    # Usuario que subió el archivo
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_files',
        help_text="Usuario que subió el archivo"
    )
    
    # Referencia al archivo anterior (para comparación)
    previous_file = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_files',
        help_text="Archivo anterior para comparación de diferencias"
    )
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Archivo de Ventas"
        verbose_name_plural = "Archivos de Ventas"
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['file_hash']),
            models.Index(fields=['content_hash']),
            models.Index(fields=['date_range_start', 'date_range_end']),
            models.Index(fields=['processed']),
        ]

    def __str__(self):
        return f"SalesFile {self.id} - {self.filename} ({self.total_rows} rows)"
    
    @staticmethod
    def calculate_file_hash(file_content):
        """Calcular SHA-256 hash del contenido del archivo."""
        return hashlib.sha256(file_content).hexdigest()
    
    @staticmethod
    def calculate_content_hash(rows_data):
        """
        Calcular hash del contenido de datos (sin headers).
        Útil para detectar si los datos cambiaron aunque el archivo sea diferente.
        """
        # Crear string de datos ordenados para hash consistente
        content_str = ""
        for row in sorted(rows_data, key=lambda x: (x.get('date', ''), x.get('store', ''), x.get('sku', ''))):
            content_str += f"{row.get('date')}|{row.get('store')}|{row.get('sku')}|{row.get('units')}|{row.get('orders')}\n"
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def delete_file(self):
        """Eliminar el archivo físico del storage S3."""
        if self.file:
            self.file.delete(save=False)
    
    def save(self, *args, **kwargs):
        """Override save para calcular hash si es nuevo."""
        super().save(*args, **kwargs)


class SalesFileRowHash(BaseModel):
    """
    Almacena el hash de cada fila del archivo para comparación rápida.
    
    Esto permite identificar exactamente qué filas cambiaron entre archivos
    sin necesidad de cargar todo el archivo anterior en memoria.
    """
    
    # Referencia al archivo
    sales_file = models.ForeignKey(
        SalesFileStorage,
        on_delete=models.CASCADE,
        related_name='row_hashes',
        help_text="Archivo al que pertenece esta fila"
    )
    
    # Clave única de la fila (date|store|sku_padre|sku_vtex)
    row_key = models.CharField(
        max_length=500,
        db_index=True,
        help_text="Clave única: date|store|sku_padre|sku_material"
    )
    
    # Hash del contenido de la fila
    row_hash = models.CharField(
        max_length=64,
        help_text="SHA-256 hash del contenido de la fila"
    )
    
    # Datos básicos para referencia rápida
    date = models.DateField(help_text="Fecha de la fila")
    store_name = models.CharField(max_length=255, help_text="Nombre de tienda")
    sku = models.CharField(max_length=100, help_text="SKU del producto")
    units = models.IntegerField(default=0, help_text="Unidades")
    orders = models.IntegerField(default=0, help_text="Órdenes")
    
    class Meta:
        ordering = ['date', 'store_name', 'sku']
        verbose_name = "Hash de Fila"
        verbose_name_plural = "Hashes de Filas"
        indexes = [
            models.Index(fields=['sales_file', 'row_key']),
            models.Index(fields=['row_key']),
            models.Index(fields=['date']),
        ]
        # Clave única compuesta
        constraints = [
            models.UniqueConstraint(
                fields=['sales_file', 'row_key'],
                name='unique_file_row_key'
            )
        ]

    def __str__(self):
        return f"RowHash {self.row_key[:50]}..."
    
    @staticmethod
    def calculate_row_hash(date, store, sku, units, orders):
        """Calcular hash de una fila específica."""
        content = f"{date}|{store}|{sku}|{units}|{orders}"
        return hashlib.sha256(content.encode()).hexdigest()
