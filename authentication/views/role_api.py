from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from authentication.models import Role
from authentication.serializers import RoleSerializer

class RoleListCreateView(ListCreateAPIView):
    """Listar roles con paginación y crear nuevos"""
    queryset = Role.objects.filter(deleted_at__isnull=True)
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]
    
    def perform_create(self, serializer):
        """Crear un rol y asignarle permisos opcionales"""
        role = serializer.save()
        permissions = self.request.data.get("permissions", [])
        if permissions:
            role.permissions.set(permissions)

class RoleDetailView(RetrieveUpdateDestroyAPIView):
    """Obtener, actualizar o eliminar un rol"""
    queryset = Role.objects.filter(deleted_at__isnull=True)
    serializer_class = RoleSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        """Actualizar un rol y modificar permisos"""
        role = serializer.save()
        permissions = self.request.data.get("permissions", [])
        if permissions:
            role.permissions.set(permissions)
