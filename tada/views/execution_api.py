from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from tada.models import ExecutionLog
from tada.serializers import ExecutionLogSerializer
import django_filters


class ExecutionLogFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(
        field_name="date", lookup_expr="exact")
    date__gte = django_filters.DateFilter(
        field_name="date", lookup_expr="gte")
    date__lte = django_filters.DateFilter(
        field_name="date", lookup_expr="lte")
    execution_type = django_filters.ChoiceFilter(
        choices=[('manual', 'Manual'), ('automatic', 'Automatic')])
    event = django_filters.ModelChoiceFilter(
        queryset=None)  # Se definirá en el __init__
    event__name = django_filters.CharFilter(
        field_name="event__name", lookup_expr="icontains")
    command = django_filters.CharFilter(
        field_name="command", lookup_expr="icontains")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from tada.models import TrafficEvent
        self.filters['event'].queryset = TrafficEvent.objects.filter(
            deleted_at__isnull=True)

    class Meta:
        model = ExecutionLog
        fields = ["date", "execution_type", "event", "event__name", "command"]


class ExecutionLogListCreateView(ListCreateAPIView):
    queryset = ExecutionLog.objects.filter(deleted_at__isnull=True)
    serializer_class = ExecutionLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ExecutionLogFilter

    def get_queryset(self):
        return ExecutionLog.objects.filter(
            deleted_at__isnull=True).select_related('event').order_by("-date", "-time")


class ExecutionLogRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = ExecutionLog.objects.filter(deleted_at__isnull=True)
    serializer_class = ExecutionLogSerializer
    permission_classes = [IsAuthenticated]


class ExecutionLogListView(ListAPIView):
    queryset = ExecutionLog.objects.filter(
        deleted_at__isnull=True).select_related('event').order_by("-date", "-time")
    serializer_class = ExecutionLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = ExecutionLogFilter
