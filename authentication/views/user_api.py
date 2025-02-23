from authentication.models import CustomUser
from authentication.serializers import UserSerializer, UserUpdateSerializer, UserUpdateSerializer2
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import ListAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from django.contrib.auth.hashers import make_password


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

    def perform_create(self, serializer):
        # Hashea la contraseña antes de guardar
        password = serializer.validated_data.get('password')
        if password:
            serializer.save(password=make_password(password))
        else:
            serializer.save()


class UserRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    """Obtener, actualizar o eliminar un usuario"""
    queryset = CustomUser.objects.all()
    serializer_class = UserUpdateSerializer2
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        # Maneja el hasheo de la contraseña si se actualiza
        password = self.request.data.get('password', None)
        if password:
            serializer.save(password=make_password(password))
        else:
            serializer.save()


# class UserListView(ListAPIView):
#     """Lista paginada de usuarios registrados"""
#     queryset = CustomUser.objects.all()
#     serializer_class = UserSerializer
#     permission_classes = [IsAuthenticated]


class UserListAllView(ListAPIView):
    """Lista paginada de usuarios registrados"""
    queryset = CustomUser.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None
