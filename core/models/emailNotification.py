from django.db import models
from django.urls import reverse
from core.models import BaseModel
from core.utils.emailThread import EmailThread


class EmailNotification(BaseModel):
    email = models.EmailField()
    notification_type = models.ManyToManyField(
        'core.EmailNotificationType',
        related_name='email_notifications'
    )

    def __str__(self):
        return self.email

    @property
    def delete_url(self):
        return reverse('dashboard:email-notifications-delete', kwargs={'pk': self.id})

    @property
    def notification_type_list(self):
        notification_types = []

        for notification_type in self.notification_type.all():
            notification_types.append(notification_type.__str__())

        return ', '.join(notification_types)

    def get_absolute_url(self):
        return reverse('dashboard:email-notifications-update', kwargs={'pk': self.id})

    @classmethod
    def get_email_notification_by_type(cls, notification_type):
        return cls.objects.filter(notification_type=notification_type, is_active=True)

    @classmethod
    def get_emails_by_type(cls, notification_type):
        return cls.get_email_notification_by_type(notification_type).values_list('email', flat=True)

    @classmethod
    def send_notification(cls, email_template, subject, email_data, notification_type, extra_emails=None, attachments=None):
        email_notification = cls.get_emails_by_type(
            notification_type=notification_type)
        email_notification = list(email_notification)
        print('Sending notifications: ', email_notification)

        if extra_emails:
            email_notification.extend(extra_emails)

        if len(email_notification) > 0:
            EmailThread(
                subject=subject,
                template=email_template,
                email_data=email_data,
                recipient_list=email_notification,
                attachments=attachments
            ).start()

    @staticmethod
    def create_url():
        return reverse('dashboard:email-notifications-create')
