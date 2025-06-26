from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from authentication.services.auth_service import authenticate_user
from authentication.serializers.user_serializer import UserSerializer
from rest_framework.permissions import AllowAny, IsAuthenticated
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import RefreshToken
from authentication.models import CustomUser
from rest_framework_simplejwt.views import TokenRefreshView
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        password = request.data.get('password')

        try:
            tokens = authenticate_user(email, password)
            user = CustomUser.objects.get(email=email)
            user_data = UserSerializer(user).data

            response = JsonResponse({
                "access_token": tokens['access'],
                "user": user_data
            })

            # Guardar el refreshToken en una cookie segura SI
            response.set_cookie(
                key="refreshToken",
                value=str(tokens["refresh"]),
                httponly=True,
                secure=True,
                samesite="None",
                domain=".heimdal.ec",
                max_age=7 * 24 * 60 * 60,
            )

            return response

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
            refresh_token = request.COOKIES.get("refreshToken")
            if not refresh_token:
                return Response({"error": "No refresh token found"}, status=status.HTTP_400_BAD_REQUEST)

            # Blacklistear el refreshToken
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as e:
                return Response({"error": f"Invalid refresh token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # Eliminar la cookie del refreshToken
            response = Response(
                {"message": "Logout successful"}, status=status.HTTP_200_OK)
            response.delete_cookie("refreshToken")

            return response

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class CustomTokenRefreshView(TokenRefreshView):
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refreshToken")

        if not refresh_token:
            return JsonResponse({"error": "No refresh token found"}, status=401)

        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)

            # Obtener el user_id desde el refresh token
            user_id = refresh.payload.get('user_id')
            user = CustomUser.objects.get(id=user_id)
            user_data = UserSerializer(user).data

            return JsonResponse({
                "access_token": access_token,
                "user": user_data
            })
        except CustomUser.DoesNotExist:
            return JsonResponse({"error": "User not found"}, status=404)
        except Exception as e:
            return JsonResponse({"error": f"Invalid refresh token: {str(e)}"}, status=401)
