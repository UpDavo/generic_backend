from django.core.management.base import BaseCommand
from authentication.models import CustomUser, Role


class Command(BaseCommand):
    help = 'Inserta masivamente usuarios en la base de datos con rol Store'

    def handle(self, *args, **options):
        users_data = [
            ('Anthony Villegas', 'updavo@heimdal.ec'),
            ('Jose Luis Sanchez', 'jsanchez@heimdal.ec'),
            ('Erick Jaramillo', 'ejaramillo@heimdal.ec'),
        ]

        # Obtener el rol 'Store'
        store_role = Role.objects.get(name='Admin')

        for name, email in users_data:
            password = name.lower().replace(" ", "") + "123"
            user, created = CustomUser.objects.get_or_create(
                email=email,
                defaults={
                    'first_name': name,
                    'last_name': '',
                    'role': store_role,
                }
            )
            if created:
                user.set_password(password)
                user.is_verified = True
                user.save()
                self.stdout.write(self.style.SUCCESS(
                    f'Usuario creado: {email} | Contraseña: {password}'))
            else:
                user.role = store_role
                user.save()
                self.stdout.write(self.style.WARNING(
                    f'El usuario ya existe y se asignó el rol Store: {email}'))
