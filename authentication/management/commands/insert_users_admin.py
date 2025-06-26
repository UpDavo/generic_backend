import random
import string
from django.core.management.base import BaseCommand
from authentication.models import CustomUser, Role


class Command(BaseCommand):
    help = 'Inserta masivamente usuarios en la base de datos con rol Customer Service'

    def generate_password(self, length=8):
        chars = string.ascii_letters + string.digits
        return ''.join(random.choices(chars, k=length))

    def handle(self, *args, **options):
        users_data = [
            # ('Anthony Villegas', 'updavo@heimdal.ec'),
            # ('Jose Luis Sanchez', 'jsanchez@heimdal.ec'),
            # ('Erick Jaramillo', 'ejaramillo@heimdal.ec'),
            ('Jocelyne Carrillo', 'jocelyne.carrillo@ab-inbev.com'),
            ('Ulises Hernandez', 'edgar.hernandez.a@ab-inbev.com'),
        ]

        # Obtener el rol 'Customer Service'
        try:
            cs_role = Role.objects.get(name='Customer Service')
        except Role.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                'El rol "Customer Service" no existe.'))
            return

        for name, email in users_data:
            password = self.generate_password()
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': name,
                    'last_name': '',
                    'role': cs_role,
                }
            )
            if created:
                user.set_password(password)
                user.is_verified = True
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Usuario creado: {email} | Contraseña: {password}'))
            else:
                user.role = cs_role
                user.save()
                self.stdout.write(self.style.WARNING(
                    f'El usuario ya existe y se asignó el rol Customer Service: {email}'))
