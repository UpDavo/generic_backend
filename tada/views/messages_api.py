from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from tada.models import NotificationMessage, NotificationLog
from tada.serializers import NotificationMessageSerializer, NotificationLogSerializer


class NotificationMessageListCreateView(ListCreateAPIView):
    queryset = NotificationMessage.objects.all()
    serializer_class = NotificationMessageSerializer
    permission_classes = [IsAuthenticated]


class NotificationMessageRetrieveUpdateDestroyView(RetrieveUpdateDestroyAPIView):
    queryset = NotificationMessage.objects.all()
    serializer_class = NotificationMessageSerializer
    permission_classes = [IsAuthenticated]


class NotificationLogListView(ListAPIView):
    queryset = NotificationLog.objects.all()
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAuthenticated]
