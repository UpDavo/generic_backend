from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from authentication.services.auth_service import authenticate_user
from authentication.serializers.user_serializer import UserSerializer
from rest_framework.permissions import AllowAny
from django.contrib.auth.hashers import make_password
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from authentication.models import CustomUser


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        try:
            tokens = authenticate_user(email, password)
            user = CustomUser.objects.get(email=email)
            user_data = UserSerializer(user).data

            return Response({
                "tokens": tokens,
                "user": user_data
            }, status=status.HTTP_200_OK)

        except CustomUser.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(password=make_password(request.data['password']))
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if not refresh_token:
                return Response({"error": "Refresh token is required"}, status=status.HTTP_400_BAD_REQUEST)

            # 1) Blacklistear el refresh
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                return Response({"error": f"Invalid refresh token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # 2) Eliminar la sesión de la BD (Access)
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                current_access = auth_header.split(' ')[1]
                # Borrar la sesión que coincida con ese access
                from authentication.models import ActiveSession
                ActiveSession.objects.filter(
                    user=request.user,
                    access_token=current_access
                ).delete()

            return Response({"message": "Logout successful"}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
