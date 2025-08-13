from io import BytesIO
from django.http import HttpResponse
import openpyxl
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from tada.models import CanvasMessage, CanvasLog
from tada.serializers import CanvasMessageSerializer, CanvasLogSerializer
import django_filters
from authentication.models import CustomUser


class CanvasLogFilter(django_filters.FilterSet):
    sent_at = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="exact")
    sent_at__gte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="gte")
    sent_at__lte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="lte")

    user = django_filters.ModelMultipleChoiceFilter(
        queryset=CustomUser.objects.all(),
        field_name="user__email",
        to_field_name="email"
    )

    class Meta:
        model = CanvasLog
        fields = ["sent_at", "user"]


class CanvasLogRangeFilter(django_filters.FilterSet):
    sent_at__gte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="gte")
    sent_at__lte = django_filters.DateFilter(
        field_name="sent_at", lookup_expr="lte")
    user = django_filters.ModelMultipleChoiceFilter(
        queryset=CustomUser.objects.all(),
        field_name="user__email",
        to_field_name="email"
    )

    class Meta:
        model = CanvasLog
        fields = ["sent_at", "user"]


class CanvasMessageFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(
        field_name="name", lookup_expr="icontains")

    class Meta:
        model = CanvasMessage
        fields = ["name"]


class CanvasMessageListCreateView(ListCreateAPIView):
    queryset = CanvasMessage.objects.filter(deleted_at__isnull=True)
    serializer_class = CanvasMessageSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CanvasMessageFilter


class CanvasMessageRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = CanvasMessage.objects.filter(deleted_at__isnull=True)
    serializer_class = CanvasMessageSerializer
    permission_classes = [IsAuthenticated]


class CanvasLogListView(ListAPIView):
    queryset = CanvasLog.objects.filter(
        deleted_at__isnull=True).order_by("-sent_at")
    serializer_class = CanvasLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CanvasLogFilter


class CanvasLogRangeView(ListAPIView):
    """ Devuelve todos los logs en un rango de fechas sin paginación """
    queryset = CanvasLog.objects.filter(
        deleted_at__isnull=True).order_by("-sent_at")
    serializer_class = CanvasLogSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = CanvasLogRangeFilter
    pagination_class = None


class CanvasLogDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # Aplicar filtros
        f = CanvasLogRangeFilter(request.GET, queryset=CanvasLog.objects.filter(
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
        response['Content-Disposition'] = f'attachment; filename=canvas_logs.xlsx'
        return response
