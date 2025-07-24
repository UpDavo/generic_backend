import os
import tempfile
import imgkit
from django.template.loader import render_to_string
from django.conf import settings
from django.core.files.storage import default_storage
from datetime import datetime
import uuid


class HTMLToImageService:
    """Servicio para convertir plantillas HTML a imágenes"""

    def __init__(self):
        # Intentar usar binario global primero, luego local como fallback
        self.config = self._get_wkhtmltoimage_config()

        # Configuración para imgkit - removemos parámetros no compatibles
        self.options = {
            'width': 1200,
            # 'height': 800,
            'quality': 94,
            'format': 'png',
            'encoding': 'UTF-8',
        }

    def _get_wkhtmltoimage_config(self):
        """
        Obtiene la configuración de wkhtmltoimage, priorizando binarios globales
        """
        import shutil

        # 1. Intentar usar binario global del sistema
        global_binary = shutil.which('wkhtmltoimage')
        if global_binary:
            print(f"Usando binario global de wkhtmltoimage: {global_binary}")
            return imgkit.config(wkhtmltoimage=global_binary)

        # 2. Fallback: usar binario local del proyecto
        project_root = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        local_binary = os.path.join(project_root, 'bin', 'wkhtmltoimage')

        if os.path.exists(local_binary):
            print(f"Usando binario local de wkhtmltoimage: {local_binary}")
            return imgkit.config(wkhtmltoimage=local_binary)

        # 3. Si no encuentra ninguno, usar configuración por defecto
        print("No se encontró wkhtmltoimage ni global ni local, usando configuración por defecto")
        return None

    def generate_image_from_template(self, template_path, context_data):
        """
        Genera una imagen desde una plantilla HTML

        Args:
            template_path (str): Ruta de la plantilla HTML
            context_data (dict): Datos para renderizar la plantilla

        Returns:
            str: URL temporal de la imagen generada
        """
        try:
            # Renderizar la plantilla HTML con los datos
            html_content = render_to_string(template_path, context_data)

            # Generar nombre único para la imagen
            image_filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.png"

            # Crear archivo temporal
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                temp_html.write(html_content)
                temp_html_path = temp_html.name

            # Crear archivo temporal para la imagen
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_image:
                temp_image_path = temp_image.name

            # Configuración para imgkit
            options = {
                'width': 1200,
                'quality': 94,
                'format': 'png',
                'encoding': 'UTF-8',
            }

            try:
                # Convertir HTML a imagen usando la configuración apropiada
                if self.config:
                    imgkit.from_file(
                        temp_html_path, temp_image_path,
                        options=options,
                        config=self.config)
                else:
                    # Usar configuración por defecto si no hay binario específico
                    imgkit.from_file(
                        temp_html_path, temp_image_path,
                        options=options)

                # Guardar la imagen en el storage temporal (media)
                media_path = f"temp_reports/{image_filename}"

                # Leer la imagen generada y guardarla en el storage
                with open(temp_image_path, 'rb') as image_file:
                    saved_path = default_storage.save(media_path, image_file)

                # Generar URL temporal
                if hasattr(settings, 'MEDIA_URL') and hasattr(settings, 'MEDIA_ROOT'):
                    temp_url = f"{settings.MEDIA_URL}{saved_path}"
                    # Si es URL relativa, convertir a absoluta
                    if temp_url.startswith('/'):
                        # Usar la URL base del proyecto
                        base_url = settings.BASE_URL
                        temp_url = f"{base_url.rstrip('/')}{temp_url}"
                else:
                    temp_url = None

                return temp_url

            finally:
                # Limpiar archivos temporales
                try:
                    os.unlink(temp_html_path)
                    os.unlink(temp_image_path)
                except:
                    pass

        except Exception as e:
            print(f"Error al generar imagen desde HTML: {e}")
            return None

    def cleanup_temp_image(self, image_url):
        """
        Limpia una imagen temporal después de ser enviada

        Args:
            image_url (str): URL de la imagen a limpiar
        """
        try:
            if image_url and 'temp_reports/' in image_url:
                # Extraer el path relativo
                path_parts = image_url.split('temp_reports/')
                if len(path_parts) > 1:
                    relative_path = f"temp_reports/{path_parts[1]}"
                    if default_storage.exists(relative_path):
                        default_storage.delete(relative_path)
                        print(f"Imagen temporal eliminada: {relative_path}")
        except Exception as e:
            print(f"Error al limpiar imagen temporal: {e}")
