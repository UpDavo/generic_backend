from django.core.management.base import BaseCommand
from authentication.models import CustomUser, Role


class Command(BaseCommand):
    help = 'Inserta masivamente usuarios en la base de datos con rol Store'

    def handle(self, *args, **options):
        users_data = [
            ('Tada Quitumbe', 'tadaquitumbe@gmail.com'),
            ('Tada Conocoto', 'tadaarmenia@gmail.com'),
            ('Tada Gasca', 'tadagasca@gmail.com'),
            ('Tada Pomasqui', 'tadapomasqui@gmail.com'),
            ('Tada Solca', 'tadasolca@gmail.com'),
            ('Tada Sangolqui', 'tadasangolqui@gmail.com'),
            ('Tada Ordoñez Laso', 'tadaordonezlaso@gmail.com'),
            ('Tada Mariscal', 'tadamariscal1@gmail.com'),
            ('Tada Kennedy', 'tadakennedy@gmail.com'),
            ('Tada Salinas', 'tadasalinas@gmail.com'),
            ('Tada Tumbaco', 'tadatumbaco@gmail.com'),
            ('Tada SOLANDA', 'tadasanjose@gmail.com'),
            ('Tada Alborada', 'tadaalborada1@gmail.com'),
            ('Tada Vergeles', 'tadavergeles1@gmail.com'),
            ('Tada Villaflora', 'tadavillaflora@gmail.com'),
            ('Tada Calderon', 'tadacalderon@gmail.com'),
            ('Tada Condado', 'tadacondado@gmail.com'),
            ('Tada Monteserrin', 'tadamonteserrin@gmail.com'),
            ('Tada Villa del Rey', 'tadavilladelrey@gmail.com'),
            ('Tada Libertad Nuevo', 'tadalibertadnuevo@gmail.com'),
            ('Tada Manta', 'tadamanta@gmail.com'),
            ('Tada Portoviejo', 'tadaportoviejo1@gmail.com'),
            ('Tada Santa Elena', 'tadasantaelena@gmail.com'),
            ('Tada Puertas Del SOL', 'tadapuertasdelsol@gmail.com'),
            ('Tada Playas', 'tadavillamilplayas@gmail.com'),
            ('Tada Estadio', 'tadaestadio@gmail.com'),
            ('Tada Guasmo', 'tadaguasmo1@gmail.com'),
            ('Tada Yaruqui', 'tadayaruqui@gmail.com'),
        ]

        # Obtener el rol 'Store'
        store_role = Role.objects.get(name='Store')

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
