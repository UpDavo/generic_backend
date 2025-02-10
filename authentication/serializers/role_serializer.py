from rest_framework import serializers
from authentication.models import Role, Permission


class RoleSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = ["id", "name", "description", "permissions", "is_admin"]

    def get_permissions(self, obj):
        return [{"id": perm.id, "name": perm.name, "path": perm.path} for perm in obj.permissions.all()]
