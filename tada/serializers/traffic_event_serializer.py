from rest_framework import serializers
from tada.models import TrafficEvent


class TrafficEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrafficEvent
        fields = ['id', 'created_at', 'updated_at', 'braze_id', 'name']
