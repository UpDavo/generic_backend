from rest_framework import serializers
from tada.models import SKU


class SKUSimpleSerializer(serializers.ModelSerializer):
    """
    Simple serializer for SKU without nested relationships.
    Used to avoid infinite recursion in child_skus.
    """
    class Meta:
        model = SKU
        fields = [
            'id',
            'type',
            'vendor_code',
            'sku_vtex',
            'name',
            'units',
            'milliliters_per_unit',
            'units_per_box',
            'hectoliters_per_unit',
            'hectoliters_per_box',
            'homologated_names',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SKUSerializer(serializers.ModelSerializer):
    """
    Complete serializer for SKU with nested child SKUs.
    """
    child_skus = SKUSimpleSerializer(many=True, read_only=True)
    child_skus_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SKU.objects.all(),
        source='child_skus',
        write_only=True,
        required=False
    )
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SKU
        fields = [
            'id',
            'type',
            'vendor_code',
            'sku_vtex',
            'name',
            'units',
            'milliliters_per_unit',
            'units_per_box',
            'hectoliters_per_unit',
            'hectoliters_per_box',
            'homologated_names',
            'homologated_names_count',
            'child_skus',
            'child_skus_ids',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_homologated_names_count(self, obj):
        """Returns the count of homologated names."""
        return len(obj.homologated_names) if obj.homologated_names else 0
    
    def validate(self, data):
        """
        Validate that only combos can have child SKUs.
        """
        sku_type = data.get('type', self.instance.type if self.instance else None)
        child_skus = data.get('child_skus', [])
        
        if sku_type == 'principal' and child_skus:
            raise serializers.ValidationError(
                'A "principal" type SKU cannot have child SKUs. '
                'Change the type to "combo" or remove the child SKUs.'
            )
        
        return data
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        if not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("All items in homologated_names must be strings")
        
        return value


class SKUListSerializer(serializers.ModelSerializer):
    """
    Serializer for SKU listing with summary information.
    """
    children_count = serializers.SerializerMethodField()
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SKU
        fields = [
            'id',
            'type',
            'vendor_code',
            'sku_vtex',
            'name',
            'units',
            'milliliters_per_unit',
            'units_per_box',
            'hectoliters_per_unit',
            'hectoliters_per_box',
            'homologated_names_count',
            'children_count',
            'created_at'
        ]
    
    def get_children_count(self, obj):
        """Returns the number of child SKUs if it's a combo."""
        if obj.type == 'combo':
            return obj.child_skus.count()
        return 0
    
    def get_homologated_names_count(self, obj):
        """Returns the count of homologated names."""
        return len(obj.homologated_names) if obj.homologated_names else 0


class SKUCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating SKUs.
    """
    child_skus_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SKU.objects.all(),
        source='child_skus',
        required=False
    )
    
    class Meta:
        model = SKU
        fields = [
            'type',
            'vendor_code',
            'sku_vtex',
            'name',
            'units',
            'milliliters_per_unit',
            'units_per_box',
            'hectoliters_per_unit',
            'hectoliters_per_box',
            'homologated_names',
            'child_skus_ids'
        ]
    
    def validate(self, data):
        """
        Validate that only combos can have child SKUs.
        """
        sku_type = data.get('type')
        child_skus = data.get('child_skus', [])
        
        if sku_type == 'principal' and child_skus:
            raise serializers.ValidationError(
                'A "principal" type SKU cannot have child SKUs. '
                'Change the type to "combo" or remove the child SKUs.'
            )
        
        return data
    
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


class SKUUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating SKUs.
    """
    child_skus_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SKU.objects.all(),
        source='child_skus',
        required=False
    )
    
    class Meta:
        model = SKU
        fields = [
            'type',
            'vendor_code',
            'sku_vtex',
            'name',
            'units',
            'milliliters_per_unit',
            'units_per_box',
            'hectoliters_per_unit',
            'hectoliters_per_box',
            'homologated_names',
            'child_skus_ids'
        ]
    
    def validate(self, data):
        """
        Validate that only combos can have child SKUs.
        """
        sku_type = data.get('type', self.instance.type if self.instance else None)
        child_skus = data.get('child_skus', None)
        
        # If children are being updated
        if child_skus is not None:
            if sku_type == 'principal' and child_skus:
                raise serializers.ValidationError(
                    'A "principal" type SKU cannot have child SKUs. '
                    'Change the type to "combo" or remove the child SKUs.'
                )
        
        return data
    
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
