from rest_framework import serializers
from tada.models import ManualYearlyData


class ManualYearlyDataSerializer(serializers.ModelSerializer):
    """
    Serializer para el modelo ManualYearlyData.
    """
    
    class Meta:
        model = ManualYearlyData
        fields = [
            'id',
            'year',
            'start_week',
            'end_week',
            'report_type',
            'city',
            'value',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def validate_start_week(self, value):
        """Validar que la semana inicial esté en rango válido."""
        if value < 1 or value > 53:
            raise serializers.ValidationError("La semana inicial debe estar entre 1 y 53")
        return value
    
    def validate_end_week(self, value):
        """Validar que la semana final esté en rango válido."""
        if value < 1 or value > 53:
            raise serializers.ValidationError("La semana final debe estar entre 1 y 53")
        return value
    
    def validate_value(self, value):
        """Validar que el valor no sea negativo."""
        if value < 0:
            raise serializers.ValidationError("El valor no puede ser negativo")
        return value
    
    def validate(self, data):
        """Validaciones a nivel de objeto."""
        start_week = data.get('start_week')
        end_week = data.get('end_week')
        
        if start_week and end_week and start_week > end_week:
            raise serializers.ValidationError({
                'start_week': 'La semana inicial no puede ser mayor que la semana final'
            })
        
        return data


class ManualYearlyDataCreateSerializer(ManualYearlyDataSerializer):
    """
    Serializer para crear datos manuales.
    """
    
    class Meta(ManualYearlyDataSerializer.Meta):
        fields = [
            'year',
            'start_week',
            'end_week',
            'report_type',
            'city',
            'value',
        ]
