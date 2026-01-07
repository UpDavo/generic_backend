from django.contrib import admin
from tada.models import (
    NotificationLog, NotificationMessage, Price, CanvasMessage, CanvasLog,
    AppPrice, TrafficEvent, TrafficLog, ExecutionLog, DailyMeta,
    WebhookLog, SKU, POC, SalesReportLog
)


@admin.register(SalesReportLog)
class SalesReportLogAdmin(admin.ModelAdmin):
    list_display = ('id', 'filename', 'rows_processed', 'date', 'time', 'user', 'app', 'created_at')
    list_filter = ('date', 'app', 'user')
    search_fields = ('filename', 'user__email', 'user__first_name', 'user__last_name')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Información del Archivo', {
            'fields': ('filename', 'rows_processed')
        }),
        ('Timestamp', {
            'fields': ('date', 'time')
        }),
        ('Metadata', {
            'fields': ('app', 'user')
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(SKU)
class SKUAdmin(admin.ModelAdmin):
    list_display = ('id', 'sku_vtex', 'name', 'type', 'vendor_code', 'units', 'created_at')
    list_filter = ('type',)
    search_fields = ('sku_vtex', 'name', 'vendor_code')
    readonly_fields = ('created_at', 'updated_at')
    filter_horizontal = ('child_skus',)
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Información Principal', {
            'fields': ('type', 'vendor_code', 'sku_vtex', 'name', 'units')
        }),
        ('Mediciones', {
            'fields': ('milliliters_per_unit', 'units_per_box', 'hectoliters_per_unit', 'hectoliters_per_box')
        }),
        ('Relaciones', {
            'fields': ('child_skus',),
            'description': 'Solo aplica para SKUs tipo combo'
        }),
        ('Nombres Homologados', {
            'fields': ('homologated_names',),
            'description': 'Lista de nombres alternativos para matching flexible'
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(POC)
class POCAdmin(admin.ModelAdmin):
    list_display = ('id', 'id_poc', 'name', 'city', 'region', 'created_at')
    list_filter = ('region', 'city')
    search_fields = ('id_poc', 'name', 'city')
    readonly_fields = ('created_at', 'updated_at')
    ordering = ('-created_at',)
    
    fieldsets = (
        ('Información Principal', {
            'fields': ('id_poc', 'name', 'city', 'region')
        }),
        ('Nombres Homologados', {
            'fields': ('homologated_names',),
            'description': 'Lista de nombres alternativos para matching flexible'
        }),
        ('Sistema', {
            'fields': ('created_at', 'updated_at', 'deleted_at'),
            'classes': ('collapse',)
        }),
    )
