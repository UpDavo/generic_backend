from django.utils.deprecation import MiddlewareMixin
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.http import JsonResponse
from authentication.models import ActiveSession


class EnsureMaxTwoSessionsMiddleware(MiddlewareMixin):
    def process_request(self, request):
        user = request.user

        # Solo hacemos la validación si el usuario ya está autenticado
        if user and user.is_authenticated:
            jwt_auth = JWTAuthentication()
            header = jwt_auth.get_header(request)

            if header:
                # Obtener el raw token (Access Token) del header
                token = jwt_auth.get_raw_token(header)
                token_str = str(token)

                # Consultar si esa sesión está en la BD
                session_exists = ActiveSession.objects.filter(
                    user=user,
                    access_token=token_str
                ).exists()

                if not session_exists:
                    return JsonResponse(
                        {"error": "Session expired or invalid."},
                        status=401)
