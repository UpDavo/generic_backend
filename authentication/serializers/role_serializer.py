from rest_framework import serializers
from authentication.models import Role
from authentication.serializers import PermissionSerializer


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)

    class Meta:
        model = Role
        fields = ["id", "name", "description", "permissions"]
