from django.urls import path
from tada.views import *
from tada.views.logs_stats_api import NotificationLogsStatsView, CanvasLogsStatsView, CombinedLogsStatsView
from tada.views.price_history_api import PriceHistoryByAppView, AllAppsLatestPricesView, PriceComparisonView

urlpatterns = [
    # Push
    path('send/push/', SendMessage.as_view(), name='send-push'),
    path('send/canvas/', SendPushCanvas.as_view(), name='send-canvas'),

    # Messages
    path('notifications/', NotificationMessageListCreateView.as_view(),
         name='notification-list-create'),
    path('notifications/<int:pk>/',
         NotificationMessageRetrieveUpdateDestroyView.as_view(), name='notification-detail'),

    # messages notifications
    path('notification-logs/', NotificationLogListView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/', NotificationLogRangeView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/download', NotificationLogDownloadView.as_view(),
         name='notification-log-download'),

    # canvas
    path('canvas/messages/', CanvasMessageListCreateView.as_view(),
         name='canvas-message-list-create'),
    path('canvas/messages/<int:pk>/',
         CanvasMessageRetrieveUpdateDestroyView.as_view(), name='canvas-message-detail'),

    # canvas notifications
    path('canvas-logs/', CanvasLogListView.as_view(),
         name='canvas-log-list'),
    path('canvas-logs/report/', CanvasLogRangeView.as_view(),
         name='canvas-log-list'),
    path('canvas-logs/report/download', CanvasLogDownloadView.as_view(),
         name='canvas-log-download'),

    # prices
    path('prices/', PriceListCreateView.as_view(),
         name='price-list'),
    path('prices/last/', PriceLastView.as_view(),
         name='price-last'),

    # Pocs
    path('pocs/report/', PocAPI.as_view(),
         name='poc-report'),

    # app prices (CRUD básico - usa Price existente por ID)
    path('app-prices/', AppPriceListCreateView.as_view(),
         name='app-price-list-create'),
    path('app-prices/<int:pk>/',
         AppPriceRetrieveUpdateDestroyView.as_view(), name='app-price-detail'),
    path('app-prices/by-name/<str:name>/',
         AppPriceByNameView.as_view(), name='app-price-by-name'),

    # app prices con Price anidado (permite crear/editar Price junto con AppPrice)
    path('app-prices-with-price/', AppPriceWithPriceListCreateView.as_view(),
         name='app-price-with-price-list-create'),
    path('app-prices-with-price/<int:pk>/',
         AppPriceWithPriceRetrieveUpdateDestroyView.as_view(), name='app-price-with-price-detail'),

    # Estadísticas de logs por usuario con precios
    path('notification-logs/stats/', NotificationLogsStatsView.as_view(), name='notification-logs-stats'),
    path('canvas-logs/stats/', CanvasLogsStatsView.as_view(), name='canvas-logs-stats'),
    path('logs/combined-stats/', CombinedLogsStatsView.as_view(), name='combined-logs-stats'),
    
    # Historial de precios por app
    path('prices/history/<str:app>/', PriceHistoryByAppView.as_view(), name='price-history-by-app'),
    path('prices/latest-all/', AllAppsLatestPricesView.as_view(), name='latest-prices-all-apps'),
    path('prices/comparison/<str:app>/', PriceComparisonView.as_view(), name='price-comparison'),
]
