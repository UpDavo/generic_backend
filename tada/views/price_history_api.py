from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import ListAPIView
from tada.models import Price
from tada.serializers.price_serializer import PriceSerializer
from tada.utils.constants import APPS, APP_NAMES


class PriceHistoryByAppView(ListAPIView):
    """Vista para obtener el historial de precios de una app específica"""
    serializer_class = PriceSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = None

    def get_queryset(self):
        app = self.kwargs.get('app')
        return Price.objects.filter(app=app, deleted_at__isnull=True).order_by('-month')

    def list(self, request, *args, **kwargs):
        app = self.kwargs.get('app')

        # Validar que la app existe
        if app not in [str(APPS['PUSH']), str(APPS['CANVAS'])]:
            return Response({
                "error": f"App inválida. Use {APPS['PUSH']} para PUSH o {APPS['CANVAS']} para CANVAS"
            }, status=status.HTTP_400_BAD_REQUEST)

        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True)

        # Agregar información adicional
        app_name = APP_NAMES.get(int(app), app)
        latest_price = queryset.first()

        return Response({
            'app': app,
            'app_name': app_name,
            'latest_price': PriceSerializer(latest_price).data if latest_price else None,
            'total_records': queryset.count(),
            'price_history': serializer.data
        }, status=status.HTTP_200_OK)


class AllAppsLatestPricesView(APIView):
    """Vista para obtener los precios más recientes de todas las apps"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        latest_prices = []

        for app_id, app_name in APP_NAMES.items():
            latest_price = Price.get_latest_price_for_app(str(app_id))
            if latest_price:
                latest_prices.append({
                    'app': str(app_id),
                    'app_name': app_name,
                    'latest_price': PriceSerializer(latest_price).data
                })
            else:
                latest_prices.append({
                    'app': str(app_id),
                    'app_name': app_name,
                    'latest_price': None
                })

        return Response({
            'latest_prices_by_app': latest_prices
        }, status=status.HTTP_200_OK)


class PriceComparisonView(APIView):
    """Vista para comparar precios entre diferentes meses para una app"""
    permission_classes = [IsAuthenticated]

    def get(self, request, app):
        # Validar que la app existe
        if app not in [str(APPS['PUSH']), str(APPS['CANVAS'])]:
            return Response({
                "error": f"App inválida. Use {APPS['PUSH']} para PUSH o {APPS['CANVAS']} para CANVAS"
            }, status=status.HTTP_400_BAD_REQUEST)

        # Obtener historial de precios
        prices = Price.objects.filter(
            app=app, deleted_at__isnull=True).order_by('month')

        if not prices.exists():
            return Response({
                'app': app,
                'app_name': APP_NAMES.get(int(app), app),
                'message': 'No hay historial de precios para esta app'
            }, status=status.HTTP_200_OK)

        # Calcular estadísticas
        price_values = [float(p.value) for p in prices]
        min_price = min(price_values)
        max_price = max(price_values)
        avg_price = sum(price_values) / len(price_values)

        # Calcular cambios porcentuales
        price_changes = []
        previous_price = None

        for price in prices:
            if previous_price:
                change = ((float(price.value) - float(previous_price.value)
                           ) / float(previous_price.value)) * 100
                price_changes.append({
                    'from_month': previous_price.month.strftime('%Y-%m'),
                    'to_month': price.month.strftime('%Y-%m'),
                    'from_value': str(previous_price.value),
                    'to_value': str(price.value),
                    'change_percentage': round(change, 2)
                })
            previous_price = price

        return Response({
            'app': app,
            'app_name': APP_NAMES.get(int(app), app),
            'statistics': {
                'total_records': len(price_values),
                'min_price': str(min_price),
                'max_price': str(max_price),
                'avg_price': str(round(avg_price, 2))
            },
            'price_changes': price_changes,
            'full_history': PriceSerializer(prices, many=True).data
        }, status=status.HTTP_200_OK)
