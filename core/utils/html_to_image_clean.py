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
        # Configurar wkhtmltoimage automáticamente
        self.config = self._get_wkhtmltoimage_config()

        # Configuración para imgkit
        self.options = {
            'width': 1200,
            'quality': 94,
            'format': 'png',
            'encoding': 'UTF-8',
        }

    def _get_wkhtmltoimage_config(self):
        """
        Obtiene la configuración de wkhtmltoimage, priorizando binarios del sistema
        """
        import shutil

        # 1. Intentar usar binario del sistema (instalado por nixpacks)
        system_binary = shutil.which('wkhtmltoimage')
        if system_binary:
            print(f"✅ Usando wkhtmltoimage del sistema: {system_binary}")
            # En entornos sin display, usar xvfb-run automáticamente
            if shutil.which('xvfb-run') and os.environ.get('DISPLAY') is None:
                print("🖥️  Usando xvfb-run para entorno sin display")
                return imgkit.config(wkhtmltoimage=f"xvfb-run -a {system_binary}")
            return imgkit.config(wkhtmltoimage=system_binary)

        # 2. Fallback: binario local del proyecto (solo si no hay del sistema)
        project_root = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        local_binary = os.path.join(project_root, 'bin', 'wkhtmltoimage')

        if os.path.exists(local_binary):
            print(f"⚠️  Usando binario local (fallback): {local_binary}")
            return imgkit.config(wkhtmltoimage=local_binary)

        # 3. Usar configuración por defecto (sin binario específico)
        print("❌ No se encontró wkhtmltoimage, usando configuración por defecto")
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

            try:
                # Convertir HTML a imagen usando la configuración apropiada
                if self.config:
                    imgkit.from_file(
                        temp_html_path, temp_image_path,
                        options=self.options,
                        config=self.config)
                else:
                    # Usar configuración por defecto si no hay binario específico
                    imgkit.from_file(
                        temp_html_path, temp_image_path,
                        options=self.options)

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
