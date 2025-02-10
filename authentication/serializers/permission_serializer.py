from rest_framework import serializers
from authentication.models import Permission, HttpMethod


class PermissionSerializer(serializers.ModelSerializer):
    methods = serializers.SerializerMethodField()

    class Meta:
        model = Permission
        fields = ["id", "name", "path", "methods", "description"]

    def get_methods(self, obj):
        """Devuelve los métodos HTTP como una lista de diccionarios con ID y nombre."""
        return [{"id": method.id, "name": method.name} for method in obj.methods.all()]
