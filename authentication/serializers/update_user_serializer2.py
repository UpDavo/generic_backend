from rest_framework import serializers
from authentication.models import CustomUser, Role
from django.contrib.auth.hashers import make_password


class UserUpdateSerializer2(serializers.ModelSerializer):
    role = serializers.PrimaryKeyRelatedField(
        queryset=Role.objects.all(), required=False
    )
    role_name = serializers.SerializerMethodField()
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = CustomUser
        fields = ["id", "email", "first_name", "last_name",
                  "phone_number", "is_verified", "role", "role_name", "password"]

    def get_role_name(self, obj):
        return obj.role.name if obj.role else None

    def create(self, validated_data):
        """Crea un nuevo usuario con la contraseña hasheada"""
        password = validated_data.pop('password')
        user = CustomUser.objects.create(**validated_data)
        user.set_password(password)  # Esto hashea la contraseña correctamente
        user.save()
        return user

    def update(self, instance, validated_data):
        """Actualiza un usuario, hasheando la contraseña si se proporciona"""
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)  # Hashea la contraseña
        instance.save()
        return instance
