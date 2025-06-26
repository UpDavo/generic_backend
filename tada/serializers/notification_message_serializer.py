from rest_framework import serializers
from tada.models import NotificationMessage


class NotificationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationMessage
        fields = ['id', 'created_at', 'notification_type',
                  'name', 'title', 'message']
