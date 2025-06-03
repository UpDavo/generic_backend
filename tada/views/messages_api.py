from io import BytesIO
from django.http import HttpResponse
import openpyxl
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView, RetrieveAPIView
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from tada.models import NotificationMessage, NotificationLog, Price
from tada.serializers import NotificationMessageSerializer, NotificationLogSerializer, PriceSerializer
import django_filters
from authentication.models import CustomUser


class NotificationLogFilter(django_filters.FilterSet):
    sent_at = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="exact")
    sent_at__gte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="gte")
    sent_at__lte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="lte")

    user = django_filters.ModelMultipleChoiceFilter(
        queryset=CustomUser.objects.all(),
        field_name="user__email",   # <--- Importante: referencia al email
        to_field_name="email"
    )

    class Meta:
        model = NotificationLog
        fields = ["sent_at", "user"]


class NotificationLogRangeFilter(django_filters.FilterSet):
    sent_at__gte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="gte")
    sent_at__lte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="lte")
    user = django_filters.ModelMultipleChoiceFilter(
        queryset=CustomUser.objects.all(),
        field_name="user__email",   # <--- Importante: referencia al email
        to_field_name="email"
    )

    class Meta:
        model = NotificationLog
        fields = ["sent_at", "user"]


class NotificationMessageFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains")

    class Meta:
        model = NotificationMessage
        fields = ["name"]


class PriceListCreateView(ListCreateAPIView):
    queryset = Price.objects.filter(deleted_at__isnull=True)
    serializer_class = PriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class PriceLastView(RetrieveAPIView):
    serializer_class = PriceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        return Price.objects.filter(deleted_at__isnull=True).order_by('-month').first()


class NotificationMessageListCreateView(ListCreateAPIView):
    queryset = NotificationMessage.objects.filter(deleted_at__isnull=True)
    serializer_class = NotificationMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = NotificationMessageFilter


class NotificationMessageRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = NotificationMessage.objects.filter(deleted_at__isnull=True)
    serializer_class = NotificationMessageSerializer
    permission_classes = [IsAuthenticated]


class NotificationLogListView(ListAPIView):
    queryset = NotificationLog.objects.filter(
        deleted_at__isnull=True).order_by("-sent_at")
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = NotificationLogFilter


class NotificationLogRangeView(ListAPIView):
    """ Devuelve todos los logs en un rango de fechas sin paginación """
    queryset = NotificationLog.objects.filter(
        deleted_at__isnull=True).order_by("-sent_at")
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = NotificationLogRangeFilter
    pagination_class = None


class NotificationLogDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Aplicar filtros
        f = NotificationLogRangeFilter(request.GET, queryset=NotificationLog.objects.filter(
            deleted_at__isnull=True).select_related("user").order_by("-sent_at"))
        logs = f.qs

        # Crear workbook
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Logs de notificación"

        # Cabeceras
        headers = ["Email", "Tipo", "Mensaje",
                   "Fecha de envío", "Usuario", "Título"]
        ws.append(headers)

        # Contenido
        for log in logs:
            ws.append([
                log.email,
                log.notification_type,
                log.message,
                log.sent_at.strftime(
                    "%Y-%m-%d %H:%M:%S") if log.sent_at else "",
                log.user.email if log.user else "",
                log.title,
            ])

        # Preparar archivo
        output = BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename=notification_logs.xlsx'
        return response
