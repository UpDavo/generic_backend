from authentication.models import CustomUser
from authentication.serializers import UserSerializer, UserUpdateSerializer, UserUpdateSerializer2
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView


class UserDetailUpdateView(APIView):
    """Obtener y actualizar el usuario autenticado"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Obtener los datos del usuario autenticado"""
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request):
        """Actualizar la información del usuario autenticado, incluyendo el rol"""
        serializer = UserUpdateSerializer(
            request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserListCreateView(ListCreateAPIView):
    """Lista paginada y creación de usuarios"""
    queryset = CustomUser.objects.all()
    serializer_class = UserUpdateSerializer2
    permission_classes = [IsAuthenticated]


class UserRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    """Obtener, actualizar o eliminar un usuario"""
    queryset = CustomUser.objects.all()
    serializer_class = UserUpdateSerializer2
    permission_classes = [IsAuthenticated]


class UserListAllView(ListAPIView):
    """Lista paginada de usuarios registrados"""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class UsersByRoleView(APIView):
    """Obtener usuarios filtrados por rol"""
    permission_classes = [IsAuthenticated]

    def get(self, request, role_name):
        """
        Obtiene la lista de usuarios que tienen un rol específico.
        
        Args:
            role_name: Nombre del rol a filtrar (ej: 'Store')
        
        Returns:
            Lista de usuarios con ese rol
        """
        try:
            # Filtrar usuarios por rol (case-insensitive) y activos
            users = CustomUser.objects.filter(
                role__name__iexact=role_name,
                is_active=True
            ).select_related('role').order_by('email')
            
            # Serializar resultados
            results = []
            for user in users:
                # Usar first_name y last_name del AbstractUser
                full_name = f"{user.first_name} {user.last_name}".strip() or user.email
                
                results.append({
                    'id': user.id,
                    'email': user.email,
                    'name': full_name,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'phone_number': user.phone_number,
                    'role': {
                        'id': user.role.id if user.role else None,
                        'name': user.role.name if user.role else None,
                        'is_admin': user.role.is_admin if user.role else False
                    },
                    'is_active': user.is_active,
                    'date_joined': user.date_joined.isoformat() if hasattr(user, 'date_joined') else None
                })
            
            return Response({
                'role_name': role_name,
                'count': len(results),
                'users': results
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'error': 'Error obteniendo usuarios por rol',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
