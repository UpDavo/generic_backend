from rest_framework import serializers
from tada.models.app_price import AppPrice
from tada.models import Price
from tada.serializers.price_serializer import PriceSerializer
from tada.utils.constants import APP_NAMES, APPS


class AppPriceSerializer(serializers.ModelSerializer):
    price_details = PriceSerializer(source='price', read_only=True)
    app_name = serializers.SerializerMethodField()

    class Meta:
        model = AppPrice
        fields = ["id", "app", "app_name", "name", "price", "price_details", "description",
                  "created_at", "updated_at", "deleted_at"]

    def get_app_name(self, obj):
        """Obtener el nombre legible de la app"""
        try:
            app_id = int(obj.app)
            return APP_NAMES.get(app_id, obj.app)
        except (ValueError, TypeError):
            return obj.app


class AppPriceWithPriceSerializer(serializers.ModelSerializer):
    """Serializer que permite crear/actualizar AppPrice junto con Price anidado"""
    price_data = serializers.DictField(write_only=True, required=False)
    price_details = PriceSerializer(source='price', read_only=True)
    app_name = serializers.SerializerMethodField()

    class Meta:
        model = AppPrice
        fields = ["id", "app", "app_name", "name", "price", "price_data", "price_details", "description",
                  "created_at", "updated_at", "deleted_at"]
        extra_kwargs = {
            'price': {'required': False}
        }

    def get_app_name(self, obj):
        """Obtener el nombre legible de la app"""
        try:
            app_id = int(obj.app)
            return APP_NAMES.get(app_id, obj.app)
        except (ValueError, TypeError):
            return obj.app

    def validate_name(self, value):
        """Validar que el nombre sea único (excluyendo registros eliminados)"""
        instance = getattr(self, 'instance', None)
        if AppPrice.objects.filter(name=value, deleted_at__isnull=True).exclude(pk=instance.pk if instance else None).exists():
            raise serializers.ValidationError(
                "Ya existe un AppPrice con este nombre.")
        return value

    def create(self, validated_data):
        price_data = validated_data.pop('price_data', None)

        if price_data:
            # Asignar la misma app del AppPrice al Price
            price_data['app'] = validated_data.get('app', str(APPS['PUSH']))

            # Crear nuevo Price si se proporciona price_data
            price_serializer = PriceSerializer(data=price_data)
            if price_serializer.is_valid(raise_exception=True):
                price = price_serializer.save()
                validated_data['price'] = price
        elif 'price' not in validated_data:
            raise serializers.ValidationError(
                "Debe proporcionar 'price' (ID existente) o 'price_data' (nuevo precio).")

        return super().create(validated_data)

    def update(self, instance, validated_data):
        price_data = validated_data.pop('price_data', None)

        if price_data:
            # Crear un nuevo Price para mantener historial (no actualizar el existente)
            # Asignar la misma app del AppPrice al nuevo Price
            price_data['app'] = validated_data.get('app', instance.app)

            # Crear nuevo Price para el historial
            price_serializer = PriceSerializer(data=price_data)
            if price_serializer.is_valid(raise_exception=True):
                new_price = price_serializer.save()
                validated_data['price'] = new_price

        return super().update(instance, validated_data)

        return super().update(instance, validated_data)
