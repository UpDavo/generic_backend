from rest_framework import serializers
from tada.models import NotificationLog
from authentication.serializers import SimpleUserSerializer


class NotificationLogSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer()

    class Meta:
        model = NotificationLog
        fields = ["id", "email", "notification_type",
                  "message", "sent_at", "user", "title"]
