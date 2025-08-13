from rest_framework import serializers
from tada.models import Price
from tada.utils.constants import APP_NAMES


class PriceSerializer(serializers.ModelSerializer):
    app_name = serializers.SerializerMethodField()

    class Meta:
        model = Price
        fields = ["id", "app", "app_name", "month", "value", "created_at", "updated_at"]
    
    def get_app_name(self, obj):
        """Obtener el nombre legible de la app"""
        try:
            app_id = int(obj.app)
            return APP_NAMES.get(app_id, obj.app)
        except (ValueError, TypeError):
            return obj.app
