from rest_framework_simplejwt.tokens import RefreshToken
from authentication.models import CustomUser, ActiveSession
from rest_framework import serializers
from django.contrib.auth import authenticate


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'phone_number', 'is_verified']


def get_tokens_for_user(user):
    # Genera un nuevo par de tokens
    refresh = RefreshToken.for_user(user)
    access_token_str = str(refresh.access_token)

    # Verificar cuántas sesiones activas hay
    current_sessions = ActiveSession.objects.filter(user=user).count()

    # Si ya tiene 2 sesiones activas, borramos la más antigua
    if current_sessions >= 2:
        oldest_session = ActiveSession.objects.filter(
            user=user).earliest('created_at')
        oldest_session.delete()

    # Crear la nueva sesión con el Access Token
    ActiveSession.objects.create(
        user=user,
        access_token=access_token_str
    )

    return {
        'refresh': str(refresh),
        'access': access_token_str
    }


def authenticate_user(email, password):
    # Esto llama al backend de auth
    user = authenticate(username=email, password=password)

    if user is not None:
        return get_tokens_for_user(user)
    else:
        raise Exception("Credenciales inválidas o usuario no encontrado")
