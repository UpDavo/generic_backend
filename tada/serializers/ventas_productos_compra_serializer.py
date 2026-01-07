from rest_framework import serializers
from tada.models import VentasProductosCompra


class VentasProductosCompraSimpleSerializer(serializers.ModelSerializer):
    """
    Simple serializer for VentasProductosCompra without nested relationships.
    """
    class Meta:
        model = VentasProductosCompra
        fields = [
            'id',
            'code',
            'name',
            'homologated_names',
            'mililiters_per_unit',
            'box_units',
            'primary_can',
            'returnable',
            'origen',
            'cost_per_unit',
            'cost_per_box',
            'cost_per_hectoliter',
            'brand',
            'category',
            'hectoliter_per_unit',
            'hectoliter_box',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class VentasProductosCompraSerializer(serializers.ModelSerializer):
    """
    Complete serializer for VentasProductosCompra.
    """
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = VentasProductosCompra
        fields = [
            'id',
            'code',
            'name',
            'homologated_names',
            'homologated_names_count',
            'mililiters_per_unit',
            'box_units',
            'primary_can',
            'returnable',
            'origen',
            'cost_per_unit',
            'cost_per_box',
            'cost_per_hectoliter',
            'brand',
            'category',
            'hectoliter_per_unit',
            'hectoliter_box',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_homologated_names_count(self, obj):
        """Returns the count of homologated names."""
        return len(obj.homologated_names) if obj.homologated_names else 0
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        if not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("All items in homologated_names must be strings")
        
        return value


class VentasProductosCompraListSerializer(serializers.ModelSerializer):
    """
    Serializer for VentasProductosCompra listing with summary information.
    """
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = VentasProductosCompra
        fields = [
            'id',
            'code',
            'name',
            'brand',
            'category',
            'origen',
            'returnable',
            'cost_per_unit',
            'homologated_names_count',
            'created_at'
        ]
    
    def get_homologated_names_count(self, obj):
        """Returns the count of homologated names."""
        return len(obj.homologated_names) if obj.homologated_names else 0


class VentasProductosCompraCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating VentasProductosCompra.
    """
    class Meta:
        model = VentasProductosCompra
        fields = [
            'code',
            'name',
            'homologated_names',
            'mililiters_per_unit',
            'box_units',
            'primary_can',
            'returnable',
            'origen',
            'cost_per_unit',
            'cost_per_box',
            'cost_per_hectoliter',
            'brand',
            'category',
            'hectoliter_per_unit',
            'hectoliter_box'
        ]
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        validated = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("All items in homologated_names must be strings")
            item_stripped = item.strip()
            if item_stripped and item_stripped not in validated:
                validated.append(item_stripped)
        
        return validated


class VentasProductosCompraUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating VentasProductosCompra.
    """
    class Meta:
        model = VentasProductosCompra
        fields = [
            'code',
            'name',
            'homologated_names',
            'mililiters_per_unit',
            'box_units',
            'primary_can',
            'returnable',
            'origen',
            'cost_per_unit',
            'cost_per_box',
            'cost_per_hectoliter',
            'brand',
            'category',
            'hectoliter_per_unit',
            'hectoliter_box'
        ]
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        validated = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("All items in homologated_names must be strings")
            item_stripped = item.strip()
            if item_stripped and item_stripped not in validated:
                validated.append(item_stripped)
        
        return validated
