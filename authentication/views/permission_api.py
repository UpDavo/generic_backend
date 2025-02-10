from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from authentication.models import Permission
from authentication.serializers import PermissionSerializer


class PermissionListCreateView(ListCreateAPIView):
    """Listar permisos con paginación y crear nuevos"""
    queryset = Permission.objects.filter(deleted_at__isnull=True)
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        """Crear un permiso y asignarle métodos opcionales"""
        permission = serializer.save()
        methods = self.request.data.get("methods", [])
        if methods:
            permission.methods.set(methods)


class PermissionDetailView(RetrieveUpdateDestroyAPIView):
    """Obtener, actualizar o eliminar un permiso"""
    queryset = Permission.objects.filter(deleted_at__isnull=True)
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        """Actualizar un permiso y modificar sus métodos HTTP"""
        permission = serializer.save()
        methods = self.request.data.get("methods", [])
        if methods:
            permission.methods.set(methods)
