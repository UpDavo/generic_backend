from rest_framework import serializers
from datetime import datetime
from tada.models import DailyMeta


class DailyMetaSerializer(serializers.ModelSerializer):
    """
    Serializer para el modelo DailyMeta.
    """

    class Meta:
        model = DailyMeta
        fields = [
            'id',
            'date',
            'target_count',
            'created_at',
            'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_date(self, value):
        """
        Validar que la fecha no sea muy antigua.
        """
        if value < datetime.now().date():
            # Permitir fechas pasadas pero advertir en logs si es necesario
            pass
        return value

    def validate_target_count(self, value):
        """
        Validar que el target_count sea positivo.
        """
        if value <= 0:
            raise serializers.ValidationError(
                "La meta debe ser un número positivo mayor a 0.")
        return value


class DailyMetaCreateSerializer(DailyMetaSerializer):
    """
    Serializer específico para crear metas diarias.
    """

    def create(self, validated_data):
        """
        Crear una nueva meta diaria.
        """
        # Verificar si ya existe una meta para la fecha
        date = validated_data['date']
        existing_meta = DailyMeta.objects.filter(date=date).first()

        if existing_meta:
            raise serializers.ValidationError(
                f"Ya existe una meta para la fecha {date}. Use PUT para actualizar."
            )

        return super().create(validated_data)


class DailyMetaUpdateSerializer(DailyMetaSerializer):
    """
    Serializer específico para actualizar metas diarias.
    """

    def update(self, instance, validated_data):
        """
        Actualizar una meta diaria existente.
        """
        # No permitir cambiar la fecha en una actualización
        if 'date' in validated_data and validated_data['date'] != instance.date:
            raise serializers.ValidationError(
                "No se puede cambiar la fecha de una meta existente."
            )

        return super().update(instance, validated_data)


class DailyMetaListSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para listar metas.
    """
    work_hours_range = serializers.SerializerMethodField()

    class Meta:
        model = DailyMeta
        fields = [
            'id',
            'date',
            'target_count',
            'work_hours_range'
        ]

    def get_work_hours_range(self, obj):
        """
        Retorna el rango de horas laborales.
        """
        return obj.get_work_hours_range()
