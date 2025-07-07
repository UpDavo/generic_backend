from rest_framework import serializers
from tada.models import ExecutionLog


class ExecutionLogSerializer(serializers.ModelSerializer):
    event_name = serializers.CharField(source='event.name', read_only=True)
    event_braze_id = serializers.CharField(
        source='event.braze_id', read_only=True)

    class Meta:
        model = ExecutionLog
        fields = ['id', 'created_at', 'updated_at', 'event',
                  'event_name', 'event_braze_id', 'execution_type', 'command', 'date', 'time', 'app']
