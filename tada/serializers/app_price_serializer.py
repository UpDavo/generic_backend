from rest_framework import serializers
from tada.models.app_price import AppPrice


class AppPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppPrice
        fields = ["id", "name", "price", "description",
                  "created_at", "updated_at", "deleted_at"]
