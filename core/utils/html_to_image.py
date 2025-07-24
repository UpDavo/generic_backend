import os
import tempfile
import imgkit
from django.template.loader import render_to_string
from django.conf import settings
from datetime import datetime, timedelta
import uuid
from core.utils.storage_backend import PublicUploadStorage


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

        # Configurar storage de S3 para imágenes temporales
        try:
            self.s3_storage = PublicUploadStorage()
            self.s3_storage.location = 'temp_reports'  # Subcarpeta en el bucket
            # Eliminar el ACL para evitar errores con buckets que no permiten ACLs
            self.s3_storage.default_acl = None
            self.s3_storage.object_parameters = {
                'CacheControl': 'max-age=86400',  # Cache por 1 día
            }
            self.use_s3 = True
            print("S3 storage configurado para imágenes temporales")
        except Exception as e:
            print(f"Error configurando S3, usando storage local: {e}")
            self.s3_storage = None
            self.use_s3 = False

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

                # Intentar subir a S3, con fallback a storage local
                if self.use_s3 and self.s3_storage:
                    # Subir la imagen directamente a S3
                    s3_path = f"{image_filename}"  # Solo el nombre del archivo

                    # Leer la imagen generada y subirla a S3
                    with open(temp_image_path, 'rb') as image_file:
                        saved_path = self.s3_storage.save(s3_path, image_file)

                    # Generar URL de S3 (pública)
                    temp_url = self.s3_storage.url(saved_path)
                    print(f"Imagen temporal subida a S3: {temp_url}")
                else:
                    print("S3 no configurado correctamente")
                    return None

                return temp_url

            finally:
                # Solo limpiar archivos temporales del sistema
                try:
                    os.unlink(temp_html_path)
                    os.unlink(temp_image_path)
                except:
                    pass

        except Exception as e:
            print(f"Error al generar imagen desde HTML: {e}")
            return None
