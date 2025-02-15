from django.urls import path
from tada.views.braze_api import SendMessage
from tada.views.messages_api import NotificationMessageListCreateView, NotificationMessageRetrieveUpdateDestroyView, NotificationLogListView

urlpatterns = [
    # Push
    path('send/push/', SendMessage.as_view(), name='send'),

    # Messages
    path('notifications/', NotificationMessageListCreateView.as_view(),
         name='notification-list-create'),
    path('notifications/<int:pk>/',
         NotificationMessageRetrieveUpdateDestroyView.as_view(), name='notification-detail'),
    path('notification-logs/', NotificationLogListView.as_view(),
         name='notification-log-list'),
]
