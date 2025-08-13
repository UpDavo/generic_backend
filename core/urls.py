from django.urls import path
from core.views.notification_api import (
    EmailNotificationListAllView,
    EmailNotificationListCreateView,
    EmailNotificationDetailView,
    EmailNotificationByTypeView,
    EmailNotificationTypeListView
)

urlpatterns = [
    # Tipos de notificación
    path('notification-types/', EmailNotificationTypeListView.as_view(),
         name='email-notification-types-list'),

    # Notificaciones por email
    path('notifications/all/', EmailNotificationListAllView.as_view(),
         name='email-notifications-list-all'),
    path('notifications/', EmailNotificationListCreateView.as_view(),
         name='email-notifications-list-create'),
    path('notifications/<int:pk>/', EmailNotificationDetailView.as_view(),
         name='email-notifications-detail'),
    path('notifications/type/<int:notification_type_id>/', EmailNotificationByTypeView.as_view(),
         name='email-notifications-by-type'),
]
