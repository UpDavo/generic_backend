from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from core.models import EmailNotification, EmailNotificationType
from core.serializers.email_notification_serializer import (
    EmailNotificationSerializer,
    EmailNotificationCreateSerializer,
    EmailNotificationTypeSerializer
)


class EmailNotificationTypeListView(ListAPIView):
    """Listar todos los tipos de notificación disponibles"""
    queryset = EmailNotificationType.objects.filter(deleted_at__isnull=True)
    serializer_class = EmailNotificationTypeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class EmailNotificationListAllView(ListAPIView):
    """Listar todas las notificaciones por email sin paginación"""
    queryset = EmailNotification.objects.filter(deleted_at__isnull=True)
    serializer_class = EmailNotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class EmailNotificationListCreateView(ListCreateAPIView):
    """Listar notificaciones por email con paginación y crear nuevas"""
    queryset = EmailNotification.objects.filter(deleted_at__isnull=True)
    serializer_class = EmailNotificationSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return EmailNotificationCreateSerializer
        return EmailNotificationSerializer

    def perform_create(self, serializer):
        """Crear una notificación y asignarle tipos opcionales"""
        email_notification = serializer.save()
        notification_types = self.request.data.get("notification_type", [])
        if notification_types:
            email_notification.notification_type.set(notification_types)


class EmailNotificationDetailView(RetrieveUpdateDestroyAPIView):
    """Obtener, actualizar o eliminar una notificación por email"""
    queryset = EmailNotification.objects.filter(deleted_at__isnull=True)
    serializer_class = EmailNotificationSerializer
    permission_classes = [IsAuthenticated]

    def perform_update(self, serializer):
        """Actualizar una notificación y modificar sus tipos"""
        email_notification = serializer.save()
        notification_types = self.request.data.get("notification_type", [])
        if notification_types is not None:
            email_notification.notification_type.set(notification_types)

    def perform_destroy(self, instance):
        """Soft delete de la notificación"""
        instance.delete()


class EmailNotificationByTypeView(ListAPIView):
    """Obtener notificaciones por tipo específico"""
    serializer_class = EmailNotificationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        notification_type_id = self.kwargs.get('notification_type_id')
        return EmailNotification.objects.filter(
            notification_type=notification_type_id,
            deleted_at__isnull=True,
            is_active=True
        )
