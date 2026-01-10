from rest_framework import serializers
from datetime import datetime
from tada.models import HectolitresDailyMeta


class HectolitresDailyMetaSerializer(serializers.ModelSerializer):
    """
    Serializer para el modelo HectolitresDailyMeta.
    """

    class Meta:
        model = HectolitresDailyMeta
        fields = [
            'id',
            'date',
            'target_hectolitres',
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

    def validate_target_hectolitres(self, value):
        """
        Validar que target_hectolitres sea positivo.
        """
        if value <= 0:
            raise serializers.ValidationError(
                "La meta de hectolitros debe ser un número positivo mayor a 0.")
        return value


class HectolitresDailyMetaCreateSerializer(HectolitresDailyMetaSerializer):
    """
    Serializer específico para crear metas diarias de hectolitros.
    """

    def create(self, validated_data):
        """
        Crear una nueva meta diaria de hectolitros.
        """
        # Verificar si ya existe una meta para la fecha
        date = validated_data['date']
        existing_meta = HectolitresDailyMeta.objects.filter(date=date).first()

        if existing_meta:
            raise serializers.ValidationError(
                f"Ya existe una meta de hectolitros para la fecha {date}. Use PUT para actualizar."
            )

        return super().create(validated_data)


class HectolitresDailyMetaUpdateSerializer(HectolitresDailyMetaSerializer):
    """
    Serializer específico para actualizar metas diarias de hectolitros.
    """

    def update(self, instance, validated_data):
        """
        Actualizar una meta diaria de hectolitros existente.
        """
        # No permitir cambiar la fecha en una actualización
        if 'date' in validated_data and validated_data['date'] != instance.date:
            raise serializers.ValidationError(
                "No se puede cambiar la fecha de una meta existente."
            )

        return super().update(instance, validated_data)


class HectolitresDailyMetaListSerializer(serializers.ModelSerializer):
    """
    Serializer simplificado para listar metas de hectolitros.
    """
    work_hours_range = serializers.SerializerMethodField()

    class Meta:
        model = HectolitresDailyMeta
        fields = [
            'id',
            'date',
            'target_hectolitres',
            'work_hours_range'
        ]

    def get_work_hours_range(self, obj):
        """
        Retorna el rango de horas laborales.
        """
        return obj.get_work_hours_range()
