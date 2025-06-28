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

    # app prices
    path('app-prices/', AppPriceListCreateView.as_view(),
         name='app-price-list-create'),
    path('app-prices/by-name/<str:name>/',
         AppPriceByNameView.as_view(), name='app-price-by-name'),
]
