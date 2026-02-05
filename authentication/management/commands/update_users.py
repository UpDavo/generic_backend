from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from authentication.models import CustomUser


class Command(BaseCommand):
    help = 'Actualiza la contraseña de los usuarios creados en la lista, usando contraseñas más seguras (7 caracteres, sin símbolos)'

    def handle(self, *args, **options):
        users_data = [
            ('Karen Proaño', 'karen.proano@ab-inbev.com'),
            ('Estefano', 'estefano.chiarello.c@ab-inbev.com'),
            ('Karla Villacis', 'karla.villacis@ab-inbev.com'),
        ]

        for name, email in users_data:
            try:
                user = CustomUser.objects.get(email=email)
                # Genera una nueva contraseña de 7 caracteres (solo letras y números).
                new_password = get_random_string(
                    length=7,
                    allowed_chars='abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'
                )
                user.set_password(new_password)
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Usuario: {email} | Nueva contraseña: {new_password}'
                ))
            except CustomUser.DoesNotExist:
                self.stdout.write(self.style.ERROR(
                    f'No se encontró el usuario con email: {email}'
                ))
