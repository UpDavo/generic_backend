from django.utils.deprecation import MiddlewareMixin
from authentication.models import CustomUser
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.http import JsonResponse


class EnsureSingleSessionMiddleware(MiddlewareMixin):
    def process_request(self, request):
        if request.user.is_authenticated:
            jwt_auth = JWTAuthentication()
            header = jwt_auth.get_header(request)
            if header:
                token = jwt_auth.get_raw_token(header)
                if str(token) != request.user.active_session_token:
                    return JsonResponse(
                        {"error": "Session expired, please login again"},
                        status=401
                    )
