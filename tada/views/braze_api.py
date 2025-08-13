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
from tada.models.canvasMessage import CanvasMessage
from tada.models.canvasLog import CanvasLog

BRAZE_API_URL = settings.BRAZE_URL
BRAZE_KEY = settings.BRAZE_KEY


class SendMessage(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        emails = request.data.get('emails')
        notification_type = request.data.get('notification_type')
        print(f"Emails: {emails}, Notification Type: {notification_type}")
        braze_service = BrazeService()  # Instancia del servicio Braze

        if not emails or not notification_type:
            return Response({"error": "Se requiere email y tipo de notificación"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Obtener mensaje desde el modelo NotificationMessage
            try:
                message_obj = NotificationMessage.objects.filter(
                    notification_type=notification_type, deleted_at__isnull=True
                ).first()

                if not message_obj:
                    return Response({
                        "error": "Error al enviar la notificación",
                        "details": f"No existe mensaje para el tipo '{notification_type}'"
                    }, status=status.HTTP_404_NOT_FOUND)

                message_text = message_obj.message
                message_title = message_obj.title if message_obj.title else "Mensaje de TaDa"

            except NotificationMessage.DoesNotExist:
                return Response({"error": "Error al enviar la notificación", "details": "Tipo de mensaje no existe"}, status=status.HTTP_404_NOT_FOUND)

            users_data = braze_service.get_external_ids(emails)

            if not users_data:
                return Response({"error": "Usuarios no encontrado en Braze"}, status=status.HTTP_404_NOT_FOUND)

            try:
                external_ids = braze_service.get_most_recent_external_ids(
                    users_data)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            message_response_data, message_response = braze_service.send_push_notifications(
                external_ids, message_title, message_text)

            if message_response.status_code != 201:
                return Response({"error": "Error al enviar la notificación", "details": message_response_data}, status=status.HTTP_400_BAD_REQUEST)

            for email in emails:
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


class SendPushCanvas(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        emails = request.data.get('emails')
        notification_type = request.data.get('notification_type')
        braze_service = BrazeService()
        canvas_id = ''

        print(f"Emails: {emails}, Notification Type: {notification_type}")

        if not emails or not notification_type:
            return Response({"error": "Se requiere email y tipo de notificación"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            try:
                canvas_obj = CanvasMessage.objects.filter(
                    id=notification_type, deleted_at__isnull=True
                ).first()

                if not canvas_obj:
                    return Response({
                        "error": "Error al enviar la notificación",
                        "details": f"No existe mensaje para el tipo '{notification_type}'"
                    }, status=status.HTTP_404_NOT_FOUND)

                canvas_id = canvas_obj.braze_id

            except CanvasMessage.DoesNotExist:
                return Response({"error": "Error al enviar la notificación", "details": "Tipo de mensaje no existe"}, status=status.HTTP_404_NOT_FOUND)

            print(f"Canvas ID: {canvas_id}")

            users_data = braze_service.get_external_ids(emails)

            if not users_data:
                return Response({"error": "Usuarios no encontrado en Braze"}, status=status.HTTP_404_NOT_FOUND)

            try:
                external_ids = braze_service.get_most_recent_external_ids(
                    users_data)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            if canvas_id != '':
                message_response_data, message_response = braze_service.send_massive_campaign(
                    canvas_id, external_ids)
            else:
                return Response({"error": "ID de canvas no encontrado"}, status=status.HTTP_404_NOT_FOUND)

            if message_response.status_code != 201:
                return Response({"error": "Error al enviar la notificación", "details": message_response_data}, status=status.HTTP_400_BAD_REQUEST)

            for email in emails:
                # Guardar en el log de notificaciones
                CanvasLog.objects.create(
                    user=request.user,
                    email=email,
                    name=canvas_obj.name,
                    sent_at=now()
                )

            return Response({"message": "Notificación enviada con éxito", "dispatch_id": message_response_data.get("dispatch_id")}, status=status.HTTP_200_OK)

        except requests.exceptions.RequestException as e:
            return Response({"error": "Error en la comunicación con la API de Braze", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        except Exception as e:
            return Response({"error": "Error interno del servidor", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
