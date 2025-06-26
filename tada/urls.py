from django.urls import path
from tada.views import *

urlpatterns = [
    # Push
    path('send/push/', SendMessage.as_view(), name='send'),

    # Messages
    path('notifications/', NotificationMessageListCreateView.as_view(),
         name='notification-list-create'),
    path('notifications/<int:pk>/',
         NotificationMessageRetrieveUpdateDestroyView.as_view(), name='notification-detail'),

    # logs
    path('prices/', PriceListCreateView.as_view(),
         name='price-list'),
    path('prices/last/', PriceLastView.as_view(),
         name='price-last'),
    path('notification-logs/', NotificationLogListView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/', NotificationLogRangeView.as_view(),
         name='notification-log-list'),
    path('notification-logs/report/download', NotificationLogDownloadView.as_view(),
         name='notification-log-download'),

    # Pocs
    path('pocs/report/', PocAPI.as_view(),
         name='poc-report'),
]
