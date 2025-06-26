from rest_framework import serializers
from authentication.models import CustomUser, Role


class UserUpdateSerializer2(serializers.ModelSerializer):
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), required=False
    )
    role_name = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = ["id", "email", "first_name", "last_name",
                  "phone_number", "is_verified", "role", "role_name"]

    def get_role_name(self, obj):
        return obj.role.name if obj.role else None
