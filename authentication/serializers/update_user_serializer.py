from rest_framework import serializers
from authentication.models import CustomUser, Role


class UserUpdateSerializer(serializers.ModelSerializer):
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), required=False
    )

    class Meta:
        model = CustomUser
        fields = ["first_name", "last_name",
                  "phone_number", "is_verified", "role"]
