from rest_framework import serializers
from tada.models import POC


class POCSimpleSerializer(serializers.ModelSerializer):
    """
    Simple serializer for POC without complex logic.
    """
    class Meta:
        model = POC
        fields = [
            'id',
            'id_poc',
            'city',
            'name',
            'region',
            'homologated_names',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POCSerializer(serializers.ModelSerializer):
    """
    Complete serializer for POC.
    """
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = POC
        fields = [
            'id',
            'id_poc',
            'city',
            'name',
            'region',
            'homologated_names',
            'homologated_names_count',
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
        
        # Ensure all items are strings
        if not all(isinstance(item, str) for item in value):
            raise serializers.ValidationError("All items in homologated_names must be strings")
        
        return value


class POCListSerializer(serializers.ModelSerializer):
    """
    Serializer for POC listing with summary information.
    """
    homologated_names_count = serializers.SerializerMethodField()
    
    class Meta:
        model = POC
        fields = [
            'id',
            'id_poc',
            'city',
            'name',
            'region',
            'homologated_names_count',
            'created_at'
        ]
    
    def get_homologated_names_count(self, obj):
        """Returns the count of homologated names."""
        return len(obj.homologated_names) if obj.homologated_names else 0


class POCCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating POCs.
    """
    class Meta:
        model = POC
        fields = [
            'id_poc',
            'city',
            'name',
            'region',
            'homologated_names'
        ]
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        # Ensure all items are strings and remove duplicates
        validated = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("All items in homologated_names must be strings")
            item_stripped = item.strip()
            if item_stripped and item_stripped not in validated:
                validated.append(item_stripped)
        
        return validated


class POCUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating POCs.
    """
    class Meta:
        model = POC
        fields = [
            'id_poc',
            'city',
            'name',
            'region',
            'homologated_names'
        ]
    
    def validate_homologated_names(self, value):
        """Validate that homologated_names is a list of strings."""
        if value is None:
            return []
        
        if not isinstance(value, list):
            raise serializers.ValidationError("homologated_names must be a list")
        
        # Ensure all items are strings and remove duplicates
        validated = []
        for item in value:
            if not isinstance(item, str):
                raise serializers.ValidationError("All items in homologated_names must be strings")
            item_stripped = item.strip()
            if item_stripped and item_stripped not in validated:
                validated.append(item_stripped)
        
        return validated
