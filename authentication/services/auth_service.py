from rest_framework_simplejwt.tokens import RefreshToken
# from django.contrib.auth import authenticate
from authentication.models import CustomUser
from rest_framework import serializers
from django.core.exceptions import ObjectDoesNotExist


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'username', 'email', 'phone_number', 'is_verified']


def get_tokens_for_user(user):
    """
    Genera nuevos tokens de acceso y refresh para el usuario.
    Si ya tiene un token activo, lo revoca antes de generar uno nuevo.
    """
    # Revocar el token anterior si existe
    if user.active_session_token:
        try:
            token = RefreshToken(user.active_session_token)
            token.blacklist()  # Invalida el token anterior
        except Exception:
            pass  # El token ya puede estar vencido o inválido

    # Generar nuevos tokens
    refresh = RefreshToken.for_user(user)
    user.active_session_token = str(refresh)
    user.save(update_fields=['active_session_token'])

    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def authenticate_user(email, password):
    """
    Verifica las credenciales del usuario y genera tokens.
    """
    try:
        user = CustomUser.objects.get(email=email)
        if user.check_password(password):
            return get_tokens_for_user(user)
        else:
            raise Exception("Credenciales inválidas")
    except ObjectDoesNotExist:
        raise Exception("Usuario no encontrado")
