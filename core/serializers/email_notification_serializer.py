from rest_framework import serializers
from core.models import EmailNotification, EmailNotificationType


class EmailNotificationTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailNotificationType
        fields = ['id', 'notification_type', 'get_notification_type_display']
        read_only_fields = ['id', 'get_notification_type_display']


class EmailNotificationSerializer(serializers.ModelSerializer):
    notification_type_details = EmailNotificationTypeSerializer(
        source='notification_type', many=True, read_only=True)
    notification_type_list = serializers.CharField(read_only=True)

    class Meta:
        model = EmailNotification
        fields = [
            'id', 'email', 'notification_type', 'notification_type_details',
            'notification_type_list', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def create(self, validated_data):
        notification_types = validated_data.pop('notification_type', [])
        email_notification = EmailNotification.objects.create(**validated_data)
        if notification_types:
            email_notification.notification_type.set(notification_types)
        return email_notification

    def update(self, instance, validated_data):
        notification_types = validated_data.pop('notification_type', None)

        # Actualizar campos básicos
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Actualizar tipos de notificación si se proporcionan
        if notification_types is not None:
            instance.notification_type.set(notification_types)

        return instance


class EmailNotificationCreateSerializer(serializers.ModelSerializer):
    """Serializer simplificado para crear notificaciones"""

    class Meta:
        model = EmailNotification
        fields = ['email', 'notification_type', 'is_active']

    def create(self, validated_data):
        notification_types = validated_data.pop('notification_type', [])
        email_notification = EmailNotification.objects.create(**validated_data)
        if notification_types:
            email_notification.notification_type.set(notification_types)
        return email_notification
