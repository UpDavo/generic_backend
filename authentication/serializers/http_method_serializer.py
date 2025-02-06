from rest_framework import serializers
from authentication.models import HttpMethod


class HttpMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = HttpMethod
        fields = ["id", "name"]
