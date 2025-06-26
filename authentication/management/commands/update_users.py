from django.core.management.base import BaseCommand
from django.utils.crypto import get_random_string
from authentication.models import CustomUser


class Command(BaseCommand):
    help = 'Actualiza la contraseña de los usuarios creados en la lista, usando contraseñas más seguras (7 caracteres, sin símbolos)'

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
            # ('Tada Alborada', 'tadaalborada1@gmail.com'),
            ('Tada Vergeles', 'tadavergeles1@gmail.com'),
            ('Tada Villaflora', 'tadavillaflora@gmail.com'),
            ('Tada Calderon', 'tadacalderon@gmail.com'),
            # ('Tada Condado', 'tadacondado@gmail.com'),
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
