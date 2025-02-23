from rest_framework import serializers
from tada.models import Price


class PriceSerializer(serializers.ModelSerializer):

    class Meta:
        model = Price
        fields = ["id", "month", "value"]
