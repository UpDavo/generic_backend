from rest_framework.generics import ListCreateAPIView, RetrieveAPIView
from rest_framework.permissions import IsAuthenticated
from tada.models import Price
from tada.serializers import PriceSerializer
from tada.models.app_price import AppPrice
from tada.serializers.app_price_serializer import AppPriceSerializer


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


class AppPriceListCreateView(ListCreateAPIView):
    queryset = AppPrice.objects.filter(deleted_at__isnull=True)
    serializer_class = AppPriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None


class AppPriceByNameView(RetrieveAPIView):
    serializer_class = AppPriceSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        name = self.kwargs.get('name')
        return AppPrice.objects.filter(deleted_at__isnull=True, name=name).first()
