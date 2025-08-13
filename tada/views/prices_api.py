from rest_framework.generics import ListCreateAPIView, RetrieveAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from tada.models import Price
from tada.serializers import PriceSerializer
from tada.models.app_price import AppPrice
from tada.serializers.app_price_serializer import AppPriceSerializer, AppPriceWithPriceSerializer


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


# CRUD básico para AppPrice (usando price existente por ID)
class AppPriceListCreateView(ListCreateAPIView):
    queryset = AppPrice.objects.filter(deleted_at__isnull=True)
    serializer_class = AppPriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class AppPriceRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = AppPrice.objects.filter(deleted_at__isnull=True)
    serializer_class = AppPriceSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        # Soft delete: marcar como eliminado en lugar de borrar físicamente
        instance.deleted_at = timezone.now()
        instance.save()


class AppPriceByNameView(RetrieveAPIView):
    serializer_class = AppPriceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        name = self.kwargs.get('name')
        return AppPrice.objects.filter(deleted_at__isnull=True, name=name).first()


# CRUD con Price anidado (permite crear/editar Price junto con AppPrice)
class AppPriceWithPriceListCreateView(ListCreateAPIView):
    """Vista que permite crear AppPrice junto con Price anidado"""
    queryset = AppPrice.objects.filter(deleted_at__isnull=True)
    serializer_class = AppPriceWithPriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class AppPriceWithPriceRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    """Vista que permite actualizar AppPrice junto con Price anidado"""
    queryset = AppPrice.objects.filter(deleted_at__isnull=True)
    serializer_class = AppPriceWithPriceSerializer
    permission_classes = [IsAuthenticated]

    def perform_destroy(self, instance):
        # Soft delete: marcar como eliminado en lugar de borrar físicamente
        instance.deleted_at = timezone.now()
        instance.save()
