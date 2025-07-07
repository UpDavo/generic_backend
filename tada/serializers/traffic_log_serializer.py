from rest_framework import serializers
from tada.models import TrafficLog


class TrafficLogSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_braze_id = serializers.CharField(
        source='event.braze_id', read_only=True)

    class Meta:
        model = TrafficLog
        fields = ['id', 'created_at', 'updated_at', 'event',
                  'event_name', 'event_braze_id', 'date', 'time', 'count', 'app']
