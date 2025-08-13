from rest_framework import serializers
from tada.models import CanvasLog
from authentication.serializers import SimpleUserSerializer


class CanvasLogSerializer(serializers.ModelSerializer):
    user = SimpleUserSerializer()

    class Meta:
        model = CanvasLog
        fields = ["id", "email", "sent_at", "user", "name"]
