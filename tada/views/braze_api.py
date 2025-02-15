import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils.timezone import now
from tada.models import NotificationMessage, NotificationLog

BRAZE_API_URL = "https://rest.iad-05.braze.com"
BRAZE_KEY = settings.BRAZE_KEY


class SendMessage(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get('email')
        notification_type = request.data.get('notification_type')

        if not email or not notification_type:
            return Response({"error": "Se requiere email y tipo de notificación"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Obtener mensaje desde el modelo NotificationMessage
            try:
                message_obj = NotificationMessage.objects.get(
                    notification_type=notification_type)
                message_text = message_obj.message
            except NotificationMessage.DoesNotExist:
                return Response({"error": "Error al enviar la notificación", "details": "Tipo de mensaje no existe"}, status=status.HTTP_404_NOT_FOUND)

            # Obtener datos del usuario desde Braze
            headers = {"Authorization": f"Bearer {BRAZE_KEY}",
                       "Content-Type": "application/json"}
            user_data_payload = {
                "email_address": email,
                "fields_to_export": [
                    "first_name", "custom_attributes", "phone", "braze_id", "external_id", "user_aliases", "apps"
                ]
            }
            user_response = requests.post(
                f"{BRAZE_API_URL}/users/export/ids", json=user_data_payload, headers=headers)
            user_response_data = user_response.json()

            if "users" not in user_response_data or not user_response_data["users"]:
                return Response({"error": "Usuario no encontrado en Braze"}, status=status.HTTP_404_NOT_FOUND)

            user_info = user_response_data["users"][0]
            external_id = user_info.get("external_id")

            if not external_id:
                return Response({"error": "El usuario no tiene un external_id válido"}, status=status.HTTP_400_BAD_REQUEST)

            # Enviar mensaje push
            message_payload = {
                "external_user_ids": [external_id],
                "messages": {
                    "apple_push": {
                        "alert": message_text,
                        "sound": "default",
                        "badge": 1,
                        "content-available": True
                    },
                    "android_push": {
                        "alert": message_text,
                        "sound": "default",
                        "priority": "high",
                        "notification_channel": "default_channel"
                    }
                }
            }

            message_response = requests.post(
                f"{BRAZE_API_URL}/messages/send", json=message_payload, headers=headers)
            message_response_data = message_response.json()

            if message_response.status_code != 201:
                return Response({"error": "Error al enviar la notificación", "details": message_response_data}, status=status.HTTP_400_BAD_REQUEST)

            # Guardar en el log de notificaciones
            NotificationLog.objects.create(
                user=request.user,
                email=email,
                notification_type=notification_type,
                message=message_text,
                sent_at=now()
            )

            return Response({"message": "Notificación enviada con éxito", "dispatch_id": message_response_data.get("dispatch_id")}, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            return Response({"error": "Error en la comunicación con la API de Braze", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": "Error interno del servidor", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
