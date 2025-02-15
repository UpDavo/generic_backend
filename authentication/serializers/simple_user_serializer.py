from rest_framework import serializers
from authentication.models import CustomUser
from .role_serializer import RoleSerializer
from .permission_serializer import PermissionSerializer


class SimpleUserSerializer(serializers.ModelSerializer):

    class Meta:
        model = CustomUser
        fields = ["id", "email", "first_name", "last_name",
                  "phone_number", "is_verified"]
