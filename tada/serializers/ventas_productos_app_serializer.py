from rest_framework import serializers
from tada.models import VentasProductosApp, VentasProductosAppMaterial, VentasProductosCompra
from .ventas_productos_compra_serializer import VentasProductosCompraSimpleSerializer


class VentasProductosAppMaterialSerializer(serializers.ModelSerializer):
    """
    Serializer for the material items with quantity.
    """
    ventas_productos_compra = VentasProductosCompraSimpleSerializer(read_only=True)
    ventas_productos_compra_id = serializers.PrimaryKeyRelatedField(
        queryset=VentasProductosCompra.objects.all(),
        source='ventas_productos_compra',
        write_only=True
    )
    
    class Meta:
        model = VentasProductosAppMaterial
        fields = [
            'id',
            'ventas_productos_compra',
            'ventas_productos_compra_id',
            'quantity'
        ]


class VentasProductosAppSimpleSerializer(serializers.ModelSerializer):
    """
    Simple serializer for VentasProductosApp without nested relationships.
    Used to avoid infinite recursion.
    """
    class Meta:
        model = VentasProductosApp
        fields = [
            'id',
            'type',
            'code',
            'name',
            'unit',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class VentasProductosAppSerializer(serializers.ModelSerializer):
    """
    Complete serializer for VentasProductosApp with nested materials.
    """
    material_items = VentasProductosAppMaterialSerializer(many=True, read_only=True)
    materials_data = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        help_text='List of materials with format: [{"ventas_productos_compra_id": 1, "quantity": 2.5}, ...]'
    )
    materials_count = serializers.SerializerMethodField()
    
    class Meta:
        model = VentasProductosApp
        fields = [
            'id',
            'type',
            'code',
            'name',
            'unit',
            'material_items',
            'materials_data',
            'materials_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_materials_count(self, obj):
        """Returns the count of materials."""
        return obj.material_items.count()
    
    def validate_materials_data(self, value):
        """Validate materials data structure."""
        if not isinstance(value, list):
            raise serializers.ValidationError("materials_data must be a list")
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each material item must be a dictionary")
            
            if 'ventas_productos_compra_id' not in item:
                raise serializers.ValidationError("Each material must have 'ventas_productos_compra_id'")
            
            if 'quantity' not in item:
                raise serializers.ValidationError("Each material must have 'quantity'")
            
            try:
                float(item['quantity'])
            except (ValueError, TypeError):
                raise serializers.ValidationError("quantity must be a number")
        
        return value
    
    def create(self, validated_data):
        """Create VentasProductosApp with materials."""
        materials_data = validated_data.pop('materials_data', [])
        
        # Create the main object
        ventas_productos_app = VentasProductosApp.objects.create(**validated_data)
        
        # Add materials
        for material_data in materials_data:
            VentasProductosAppMaterial.objects.create(
                ventas_productos_app=ventas_productos_app,
                ventas_productos_compra_id=material_data['ventas_productos_compra_id'],
                quantity=material_data['quantity']
            )
        
        return ventas_productos_app
    
    def update(self, instance, validated_data):
        """Update VentasProductosApp with materials."""
        materials_data = validated_data.pop('materials_data', None)
        
        # Update main fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update materials if provided
        if materials_data is not None:
            # Delete existing materials
            instance.material_items.all().delete()
            
            # Add new materials
            for material_data in materials_data:
                VentasProductosAppMaterial.objects.create(
                    ventas_productos_app=instance,
                    ventas_productos_compra_id=material_data['ventas_productos_compra_id'],
                    quantity=material_data['quantity']
                )
        
        return instance


class VentasProductosAppListSerializer(serializers.ModelSerializer):
    """
    Serializer for VentasProductosApp listing with summary information.
    """
    materials_count = serializers.SerializerMethodField()
    
    class Meta:
        model = VentasProductosApp
        fields = [
            'id',
            'type',
            'code',
            'name',
            'unit',
            'materials_count',
            'created_at'
        ]
    
    def get_materials_count(self, obj):
        """Returns the number of materials."""
        return obj.material_items.count()


class VentasProductosAppCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating VentasProductosApp.
    """
    materials_data = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text='List of materials with format: [{"ventas_productos_compra_id": 1, "quantity": 2.5}, ...]'
    )
    
    class Meta:
        model = VentasProductosApp
        fields = [
            'type',
            'code',
            'name',
            'unit',
            'materials_data'
        ]
    
    def validate_materials_data(self, value):
        """Validate materials data structure."""
        if not isinstance(value, list):
            raise serializers.ValidationError("materials_data must be a list")
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each material item must be a dictionary")
            
            if 'ventas_productos_compra_id' not in item:
                raise serializers.ValidationError("Each material must have 'ventas_productos_compra_id'")
            
            if 'quantity' not in item:
                raise serializers.ValidationError("Each material must have 'quantity'")
            
            try:
                float(item['quantity'])
            except (ValueError, TypeError):
                raise serializers.ValidationError("quantity must be a number")
        
        return value
    
    def create(self, validated_data):
        """Create VentasProductosApp with materials."""
        materials_data = validated_data.pop('materials_data', [])
        
        # Create the main object
        ventas_productos_app = VentasProductosApp.objects.create(**validated_data)
        
        # Add materials
        for material_data in materials_data:
            VentasProductosAppMaterial.objects.create(
                ventas_productos_app=ventas_productos_app,
                ventas_productos_compra_id=material_data['ventas_productos_compra_id'],
                quantity=material_data['quantity']
            )
        
        return ventas_productos_app


class VentasProductosAppUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating VentasProductosApp.
    """
    materials_data = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        help_text='List of materials with format: [{"ventas_productos_compra_id": 1, "quantity": 2.5}, ...]'
    )
    
    class Meta:
        model = VentasProductosApp
        fields = [
            'type',
            'code',
            'name',
            'unit',
            'materials_data'
        ]
    
    def validate_materials_data(self, value):
        """Validate materials data structure."""
        if not isinstance(value, list):
            raise serializers.ValidationError("materials_data must be a list")
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each material item must be a dictionary")
            
            if 'ventas_productos_compra_id' not in item:
                raise serializers.ValidationError("Each material must have 'ventas_productos_compra_id'")
            
            if 'quantity' not in item:
                raise serializers.ValidationError("Each material must have 'quantity'")
            
            try:
                float(item['quantity'])
            except (ValueError, TypeError):
                raise serializers.ValidationError("quantity must be a number")
        
        return value
    
    def update(self, instance, validated_data):
        """Update VentasProductosApp with materials."""
        materials_data = validated_data.pop('materials_data', None)
        
        # Update main fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update materials if provided
        if materials_data is not None:
            # Delete existing materials
            instance.material_items.all().delete()
            
            # Add new materials
            for material_data in materials_data:
                VentasProductosAppMaterial.objects.create(
                    ventas_productos_app=instance,
                    ventas_productos_compra_id=material_data['ventas_productos_compra_id'],
                    quantity=material_data['quantity']
                )
        
        return instance
