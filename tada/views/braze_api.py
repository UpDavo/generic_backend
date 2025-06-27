from datetime import datetime
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.conf import settings
from django.utils.timezone import now
from tada.models import NotificationMessage, NotificationLog
from tada.services.braze_service import BrazeService

BRAZE_API_URL = settings.BRAZE_URL
BRAZE_KEY = settings.BRAZE_KEY


class SendMessage(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get('email')
        notification_type = request.data.get('notification_type')
        braze_service = BrazeService()  # Instancia del servicio Braze

        if not email or not notification_type:
            return Response({"error": "Se requiere email y tipo de notificación"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Obtener mensaje desde el modelo NotificationMessage
            try:
                message_obj = NotificationMessage.objects.filter(
                    notification_type=notification_type, deleted_at__isnull=True).first()
                message_text = message_obj.message
                message_title = message_obj.title if message_obj.title else "Mensaje de TaDa"
            except NotificationMessage.DoesNotExist:
                return Response({"error": "Error al enviar la notificación", "details": "Tipo de mensaje no existe"}, status=status.HTTP_404_NOT_FOUND)

            user_response_data = braze_service.get_external_ids(email)

            if "users" not in user_response_data or not user_response_data["users"]:
                return Response({"error": "Usuario no encontrado en Braze"}, status=status.HTTP_404_NOT_FOUND)

            users = user_response_data["users"]

            try:
                external_id = braze_service.get_most_recent_external_id(users)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            message_response_data, message_response = braze_service.send_push_notification(
                external_id, message_title, message_text)

            if message_response.status_code != 201:
                return Response({"error": "Error al enviar la notificación", "details": message_response_data}, status=status.HTTP_400_BAD_REQUEST)

            # Guardar en el log de notificaciones
            NotificationLog.objects.create(
                user=request.user,
                email=email,
                notification_type=notification_type,
                title=message_title,
                message=message_text,
                sent_at=now()
            )

            return Response({"message": "Notificación enviada con éxito", "dispatch_id": message_response_data.get("dispatch_id")}, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            return Response({"error": "Error en la comunicación con la API de Braze", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": "Error interno del servidor", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SendPushCampaign(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        email = request.data.get('email')
        notification_type = request.data.get('notification_type')
        braze_service = BrazeService()
        campaign_id = "f0640e50-d6d9-4f27-921d-326c4666600b"

        if not email or not notification_type:
            return Response({"error": "Se requiere email y tipo de notificación"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Obtener mensaje desde el modelo NotificationMessage
            # try:
            #     message_obj = NotificationMessage.objects.filter(
            #         notification_type=notification_type, deleted_at__isnull=True).first()
            #     message_text = message_obj.message
            #     message_title = message_obj.title if message_obj.title else "Mensaje de TaDa"
            # except NotificationMessage.DoesNotExist:
            #     return Response({"error": "Error al enviar la notificación", "details": "Tipo de mensaje no existe"}, status=status.HTTP_404_NOT_FOUND)

            user_response_data = braze_service.get_external_ids(email)

            if "users" not in user_response_data or not user_response_data["users"]:
                return Response({"error": "Usuario no encontrado en Braze"}, status=status.HTTP_404_NOT_FOUND)

            users = user_response_data["users"]

            try:
                external_id = braze_service.get_most_recent_external_id(users)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            message_response_data, message_response = braze_service.send_campaign(
                campaign_id, external_id)

            if message_response.status_code != 201:
                return Response({"error": "Error al enviar la notificación", "details": message_response_data}, status=status.HTTP_400_BAD_REQUEST)

            # Guardar en el log de notificaciones
            # NotificationLog.objects.create(
            #     user=request.user,
            #     email=email,
            #     notification_type=notification_type,
            #     title=message_title,
            #     message=message_text,
            #     sent_at=now()
            # )

            return Response({"message": "Notificación enviada con éxito", "dispatch_id": message_response_data.get("dispatch_id")}, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            return Response({"error": "Error en la comunicación con la API de Braze", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": "Error interno del servidor", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
