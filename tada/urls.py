from django.urls import path
from tada.views import *

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
    path('notification-logs/stats/', NotificationLogsStatsView.as_view(),
         name='notification-logs-stats'),
    path('canvas-logs/stats/', CanvasLogsStatsView.as_view(),
         name='canvas-logs-stats'),
    path('traffic-logs/stats/', TrafficLogsStatsView.as_view(),
         name='traffic-logs-stats'),
    path('execution-logs/stats/', ExecutionLogsStatsView.as_view(),
         name='execution-logs-stats'),
    path('logs/combined-stats/', CombinedLogsStatsView.as_view(),
         name='combined-logs-stats'),

    # Historial de precios por app
    path('prices/history/<str:app>/', PriceHistoryByAppView.as_view(),
         name='price-history-by-app'),
    path('prices/latest-all/', AllAppsLatestPricesView.as_view(),
         name='latest-prices-all-apps'),
    path('prices/comparison/<str:app>/',
         PriceComparisonView.as_view(), name='price-comparison'),

    # Traffic Events (CRUD completo)
    path('traffic-events/', TrafficEventListCreateView.as_view(),
         name='traffic-event-list-create'),
    path('traffic-events/<int:pk>/',
         TrafficEventRetrieveUpdateDestroyView.as_view(), name='traffic-event-detail'),

    # Traffic Logs (solo lectura)
    path('traffic-logs/', TrafficLogListView.as_view(),
         name='traffic-log-list'),

    # Execution Logs (CRUD completo)
    path('execution-logs/', ExecutionLogListCreateView.as_view(),
         name='execution-log-list-create'),
    path('execution-logs/<int:pk>/',
         ExecutionLogRetrieveUpdateDestroyView.as_view(), name='execution-log-detail'),
    path('execution-logs/list/', ExecutionLogListView.as_view(),
         name='execution-log-list'),

    # Daily Meta (CRUD completo)
    path('daily-meta/', DailyMetaListCreateView.as_view(),
         name='daily-meta-list-create'),
    path('daily-meta/<int:pk>/',
         DailyMetaRetrieveUpdateDestroyView.as_view(), name='daily-meta-detail'),
    path('daily-meta/bulk-create/', DailyMetaBulkCreateView.as_view(),
         name='daily-meta-bulk-create'),

]
