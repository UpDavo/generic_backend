from rest_framework import serializers
from tada.models import CanvasMessage


class CanvasMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = CanvasMessage
        fields = ['id', 'created_at', 'name', 'braze_id']
