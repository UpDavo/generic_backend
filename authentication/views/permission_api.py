from authentication.models import Permission
from authentication.serializers import PermissionSerializer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from authentication.models import Permission


class PermissionListCreateView(APIView):
    """Listar todos los permisos y crear nuevos"""
    permission_classes = [IsAdminUser]

    def get(self, request):
        permissions = Permission.objects.all()
        serializer = PermissionSerializer(permissions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = PermissionSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class PermissionDetailView(APIView):
    """Obtener, actualizar o eliminar un permiso"""
    permission_classes = [IsAdminUser]

    def get(self, request, pk):
        try:
            permission = Permission.objects.get(pk=pk)
            serializer = PermissionSerializer(permission)
            return Response(serializer.data)
        except Permission.DoesNotExist:
            return Response({"error": "Permiso no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    def put(self, request, pk):
        try:
            permission = Permission.objects.get(pk=pk)
            serializer = PermissionSerializer(permission, data=request.data)
            if serializer.is_valid():
                serializer.save()
                return Response(serializer.data)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Permission.DoesNotExist:
            return Response({"error": "Permiso no encontrado"}, status=status.HTTP_404_NOT_FOUND)

    def delete(self, request, pk):
        try:
            permission = Permission.objects.get(pk=pk)
            permission.delete()
            return Response({"message": "Permiso eliminado correctamente"}, status=status.HTTP_204_NO_CONTENT)
        except Permission.DoesNotExist:
            return Response({"error": "Permiso no encontrado"}, status=status.HTTP_404_NOT_FOUND)
