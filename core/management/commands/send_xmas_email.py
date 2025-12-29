from django.core.management.base import BaseCommand
from core.utils.emailThread import EmailThread
from django.conf import settings


class Command(BaseCommand):
    help = 'Enviar un correo de Navidad a una lista de correos usando el template xmas.'

    def handle(self, *args, **options):
        """
        Envía correos de Navidad a una lista predefinida de destinatarios.
        Configura la lista de destinatarios en el arreglo 'recipients' dentro de este método.
        Cada destinatario debe tener 'email' y 'nombre'.
        """

        # Configurar la lista de destinatarios aquí
        # Formato: [{'email': 'correo@ejemplo.com', 'nombre': 'Nombre del destinatario'}, ...]
        recipients = [
            {'email': 'updavo@gmail.com', 'nombre': 'Anthony'},
            {'email': 'leidy.batista.s@ab-inbev.com', 'nombre': 'Leidy'},
            {'email': 'capig@capig.org.ec', 'nombre': 'Cristina'},
            {'email': 'cindy.cisneros.c@ab-inbev.com', 'nombre': 'Cindy'},
            {'email': 'karen.proano@ab-inbev.com', 'nombre': 'Karen'},
            {'email': 'martha.berges@ab-inbev.com', 'nombre': 'Martha'},
            {'email': 'melissa.leon@ab-inbev.com', 'nombre': 'Melissa'},
            {'email': 'juan.rivadenaira.f@ab-inbev.com', 'nombre': 'Juan'},
            {'email': 'laura.nossa.c@ab-inbev.com', 'nombre': 'Laura'},
            {'email': 'erika.borda-ext@ab-inbev.com', 'nombre': 'Erika'},
            {'email': 'laura.ortiz-ext@ab-inbev.com', 'nombre': 'Laura'},
            {'email': 'julieth.cubides-ext@ab-inbev.com', 'nombre': 'Julieth'},
            {'email': 'ariana@casadigital.ec', 'nombre': 'Ariana'},
            {'email': 'isaiguaranda@gmail.com', 'nombre': 'Abner'},
            {'email': 'luis.carvajal@ab-inbev.com', 'nombre': 'Luis'},
            {'email': 'danialemedina@gmail.com', 'nombre': 'Daniela'},
            {'email': 'locana@heimdal.ec', 'nombre': 'Lorena'},
            {'email': 'lore_ocana@hotmail.com', 'nombre': 'Lorena'},
        ]

        if not recipients:
            self.stdout.write(self.style.WARNING(
                'No hay destinatarios configurados en el arreglo recipients.'))
            return

        subject = 'Gracias por este 2025 y felices fiestas 🥂'

        total_sent = 0
        total_errors = 0

        self.stdout.write(self.style.SUCCESS(
            f'Iniciando envío de correos a {len(recipients)} destinatarios...'))

        # Enviar un correo por cada destinario con su nombre personalizado
        for recipient in recipients:
            email = recipient.get('email')
            # Valor por defecto si no se proporciona nombre
            nombre = recipient.get('nombre', 'Amigo')

            if not email:
                self.stdout.write(self.style.WARNING(
                    f'Destinatario sin email: {recipient}'))
                continue

            try:
                # Preparar los datos para el template con el nombre personalizado
                email_data = {
                    'base_url': settings.BASE_URL,
                    'nombre': nombre,
                }

                # Enviar el correo usando EmailThread (sin notification_type, solo extra_emails)
                # EmailThread(subject, email_data, recipient_list, template)
                EmailThread(
                    subject=subject,
                    email_data=email_data,
                    recipient_list=[email],
                    template='xmas.html'
                ).start()

                total_sent += 1
                self.stdout.write(self.style.SUCCESS(
                    f'✓ Correo enviado a {nombre} ({email})'))

            except Exception as e:
                total_errors += 1
                self.stdout.write(self.style.ERROR(
                    f'✗ Error al enviar correo a {nombre} ({email}): {e}'))

        # Resumen final
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS(f'Proceso completado:'))
        self.stdout.write(self.style.SUCCESS(
            f'  • Correos enviados: {total_sent}'))
        if total_errors > 0:
            self.stdout.write(self.style.ERROR(f'  • Errores: {total_errors}'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        
