from rest_framework import serializers
from authentication.models import Permission
from authentication.serializers import HttpMethodSerializer


class PermissionSerializer(serializers.ModelSerializer):
    methods = HttpMethodSerializer(many=True, read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "name", "path", "methods", "description"]
