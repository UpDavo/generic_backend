from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from tada.models import TrafficEvent, TrafficLog
from tada.serializers import TrafficEventSerializer, TrafficLogSerializer
import django_filters


class TrafficEventFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains")
    braze_id = django_filters.CharFilter(
        field_name="braze_id", lookup_expr="icontains")

    class Meta:
        model = TrafficEvent
        fields = ["name", "braze_id"]


class TrafficLogFilter(django_filters.FilterSet):
    date = django_filters.DateFilter(
        field_name="date", lookup_expr="exact")
    date__gte = django_filters.DateFilter(
        field_name="date", lookup_expr="gte")
    date__lte = django_filters.DateFilter(
        field_name="date", lookup_expr="lte")
    event = django_filters.ModelChoiceFilter(
        queryset=TrafficEvent.objects.all())
    event__name = django_filters.CharFilter(
        field_name="event__name", lookup_expr="icontains")

    class Meta:
        model = TrafficLog
        fields = ["date", "event", "event__name"]


class TrafficEventListCreateView(ListCreateAPIView):
    queryset = TrafficEvent.objects.filter(deleted_at__isnull=True)
    serializer_class = TrafficEventSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TrafficEventFilter


class TrafficEventRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = TrafficEvent.objects.filter(deleted_at__isnull=True)
    serializer_class = TrafficEventSerializer
    permission_classes = [IsAuthenticated]


class TrafficLogListView(ListAPIView):
    queryset = TrafficLog.objects.filter(
        deleted_at__isnull=True).select_related('event').order_by("-date", "-time")
    serializer_class = TrafficLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = TrafficLogFilter
