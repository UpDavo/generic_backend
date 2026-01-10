from django.db import models
from core.models import BaseModel
from authentication.models import CustomUser


class SalesRecord(BaseModel):
    """
    Registro histórico de cada venta procesada.
    
    Este modelo almacena cada línea del consolidado de ventas para:
    1. Evitar duplicados en cargas sucesivas del Excel
    2. Mantener un histórico completo de todas las ventas
    3. Permitir consultas y análisis históricos
    
    La combinación de date + store_name + sku_vtex debe ser única para evitar duplicados,
    ya que una misma tienda no puede vender el mismo SKU dos veces en la misma fecha
    (las unidades se acumulan en un solo registro).
    """
    
    # Referencia al log de procesamiento que creó este registro
    sales_log = models.ForeignKey(
        'SalesReportLog',
        on_delete=models.CASCADE,
        related_name='records',
        help_text="Log del procesamiento que generó este registro"
    )
    
    # Usuario que procesó este registro
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sales_records',
        help_text="Usuario que procesó el reporte"
    )
    
    # ===== DATOS DE IDENTIFICACIÓN ÚNICOS (para detectar duplicados) =====
    date = models.DateField(help_text="Fecha de la venta")
    store_name = models.CharField(
        max_length=255,
        help_text="Nombre original de la tienda del Excel"
    )
    sku_vtex = models.CharField(
        max_length=100,
        help_text="SKU del material final (después de expansión)"
    )
    
    # ===== DATOS DE POC =====
    poc_id = models.CharField(max_length=100, null=True, blank=True)
    poc_name = models.CharField(max_length=255, null=True, blank=True)
    poc_homolo = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        help_text="Nombre homologado si difiere del nombre principal"
    )
    poc_city = models.CharField(max_length=100, null=True, blank=True)
    poc_region = models.CharField(max_length=100, null=True, blank=True)
    
    # ===== DATOS DE PRODUCTO PADRE (del Excel) =====
    sku_padre = models.CharField(max_length=100)
    nombre_padre = models.CharField(max_length=255, null=True, blank=True)
    
    # ===== DATOS DE TRANSACCIÓN =====
    orders = models.IntegerField(default=0, help_text="Número de pedidos")
    units = models.IntegerField(default=0, help_text="Unidades vendidas del producto padre")
    
    # ===== DATOS DE PRODUCTO MATERIAL (de productos_compra) =====
    name = models.CharField(max_length=255, null=True, blank=True)
    name_homologated = models.CharField(max_length=255, null=True, blank=True)
    category = models.CharField(max_length=100, null=True, blank=True)
    brand = models.CharField(max_length=100, null=True, blank=True)
    retornable = models.CharField(max_length=50, null=True, blank=True)
    
    # ===== MÉTRICAS DE VENTAS =====
    units_assigned = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Cantidad del material en el producto padre"
    )
    units_per_sku = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        help_text="Unidades vendidas del material (units * units_assigned)"
    )
    unidades_por_caja = models.IntegerField(null=True, blank=True)
    venta_pack = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    mililitros = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True
    )
    hectolitros = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True
    )
    dolars = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )
    
    # ===== DATOS DE FECHA (derivados) =====
    week = models.IntegerField(null=True, blank=True)
    year = models.IntegerField(null=True, blank=True)
    month = models.IntegerField(null=True, blank=True)
    day = models.IntegerField(null=True, blank=True)
    dayname = models.CharField(max_length=20, null=True, blank=True)
    year_month = models.CharField(max_length=10, null=True, blank=True)
    
    class Meta:
        ordering = ['-date', 'poc_name', 'sku_vtex']
        indexes = [
            models.Index(fields=['date', 'store_name', 'sku_vtex']),
            models.Index(fields=['-date']),
            models.Index(fields=['poc_id']),
            models.Index(fields=['sku_padre']),
            models.Index(fields=['sku_vtex']),
            models.Index(fields=['sales_log']),
            models.Index(fields=['year', 'month']),
        ]
        # Constraint para evitar duplicados: misma fecha + tienda + SKU material
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'store_name', 'sku_vtex'],
                condition=models.Q(deleted_at__isnull=True),
                name='unique_sale_record'
            )
        ]
    
    def __str__(self):
        return f"Sale {self.date} - {self.store_name} - {self.sku_vtex} ({self.units_per_sku} units)"
