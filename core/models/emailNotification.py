from django.db import models
from django.urls import reverse
from core.models import BaseModel
from core.utils.emailThread import EmailThread


class EmailNotification(BaseModel):
    email = models.EmailField(blank=True, null=True)
    number = models.CharField(max_length=100, blank=True, null=True)
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
    def get_emails_by_type_id(cls, notification_type_id):
        """Obtener emails por ID de tipo de notificación"""
        return cls.objects.filter(
            notification_type__id=notification_type_id,
            is_active=True,
            deleted_at__isnull=True
        ).values_list('email', flat=True)

    @classmethod
    def get_emails_by_type_constant(cls, notification_type_constant):
        """Obtener emails por constante de tipo de notificación"""
        return cls.objects.filter(
            notification_type__notification_type=notification_type_constant,
            is_active=True,
            deleted_at__isnull=True
        ).values_list('email', flat=True)

    @classmethod
    def get_numbers_by_type_constant(cls, notification_type_constant):
        """Obtener números de teléfono por constante de tipo de notificación"""
        return cls.objects.filter(
            notification_type__notification_type=notification_type_constant,
            is_active=True,
            deleted_at__isnull=True,
            number__isnull=False,
            number__gt=''
        ).values_list('number', flat=True)

    @classmethod
    def add_email_to_type(cls, email, notification_type_id):
        """Agregar un email a un tipo de notificación específico"""
        from core.models import EmailNotificationType

        try:
            notification_type = EmailNotificationType.objects.get(
                id=notification_type_id)
            email_notification, created = cls.objects.get_or_create(
                email=email,
                defaults={'is_active': True}
            )
            email_notification.notification_type.add(notification_type)
            return email_notification, created
        except EmailNotificationType.DoesNotExist:
            return None, False

    @classmethod
    def remove_email_from_type(cls, email, notification_type_id):
        """Remover un email de un tipo de notificación específico"""
        from core.models import EmailNotificationType

        try:
            notification_type = EmailNotificationType.objects.get(
                id=notification_type_id)
            email_notification = cls.objects.get(email=email)
            email_notification.notification_type.remove(notification_type)

            # Si no tiene más tipos de notificación, eliminar el registro
            if not email_notification.notification_type.exists():
                email_notification.delete()

            return True
        except (EmailNotificationType.DoesNotExist, cls.DoesNotExist):
            return False

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

    @classmethod
    def send_notification_by_type_constant(cls, email_template, subject, email_data, notification_type_constant, extra_emails=None, attachments=None):
        """Enviar notificación usando la constante del tipo de notificación"""
        email_notification = cls.get_emails_by_type_constant(
            notification_type_constant=notification_type_constant)
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
                # recipient_list=['updavo@gmail.com'],
                attachments=attachments
            ).start()

    @staticmethod
    def create_url():
        return reverse('dashboard:email-notifications-create')
