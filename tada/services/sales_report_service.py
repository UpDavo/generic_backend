"""
Servicio para envío de reportes de ventas por WhatsApp.
"""

import base64
import uuid
import time
from datetime import datetime
from io import BytesIO

from core.models import EmailNotification, EmailNotificationType
from core.services.whatsapp_service import WhatsAppService
from core.utils.storage_backend import PublicUploadStorage


class SalesReportService:
    """
    Servicio para enviar reportes de ventas por WhatsApp.
    """

    def __init__(self):
        self.whatsapp_service = WhatsAppService()
        self._setup_s3_storage()

    def _setup_s3_storage(self):
        """Configura el storage de S3 para subir imágenes."""
        try:
            self.s3_storage = PublicUploadStorage()
            self.s3_storage.location = 'temp_reports'  # Subcarpeta en el bucket
            # Eliminar el ACL para evitar errores con buckets que no permiten ACLs
            self.s3_storage.default_acl = None
            self.s3_storage.object_parameters = {
                'CacheControl': 'max-age=86400',  # Cache por 1 día
            }
            self.use_s3 = True
            print("S3 storage configurado para reportes de ventas")
        except Exception as e:
            print(f"Error configurando S3: {e}")
            self.s3_storage = None
            self.use_s3 = False

    def upload_base64_image_to_s3(self, base64_image: str, filename_prefix: str = "sales_report") -> str:
        """
        Sube una imagen en base64 a S3 y retorna la URL pública.

        Args:
            base64_image (str): Imagen codificada en base64 (puede incluir o no el prefijo data:image/...)
            filename_prefix (str): Prefijo para el nombre del archivo

        Returns:
            str: URL pública de la imagen en S3, o None si falla
        """
        if not self.use_s3 or not self.s3_storage:
            print("❌ S3 no está configurado")
            return None

        try:
            # Remover el prefijo data:image/xxx;base64, si existe
            if ',' in base64_image:
                # Formato: data:image/png;base64,iVBORw0KGgo...
                header, base64_data = base64_image.split(',', 1)
                # Detectar extensión del header
                if 'png' in header.lower():
                    extension = 'png'
                elif 'jpg' in header.lower() or 'jpeg' in header.lower():
                    extension = 'jpg'
                elif 'gif' in header.lower():
                    extension = 'gif'
                elif 'webp' in header.lower():
                    extension = 'webp'
                else:
                    extension = 'png'  # Default
            else:
                base64_data = base64_image
                extension = 'png'  # Default si no hay header

            # Decodificar base64
            image_data = base64.b64decode(base64_data)

            # Generar nombre único para la imagen
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            unique_id = uuid.uuid4().hex[:8]
            image_filename = f"{filename_prefix}_{timestamp}_{unique_id}.{extension}"

            # Crear BytesIO con los datos de la imagen
            image_file = BytesIO(image_data)
            image_file.seek(0)

            # Subir a S3
            saved_path = self.s3_storage.save(image_filename, image_file)

            # Obtener URL pública
            image_url = self.s3_storage.url(saved_path)
            print(f"✅ Imagen subida a S3: {image_url}")

            return image_url

        except Exception as e:
            print(f"❌ Error al subir imagen a S3: {e}")
            return None

    def send_sales_report_by_whatsapp(self, image_base64: str, title: str) -> dict:
        """
        Envía un reporte de ventas por WhatsApp a los números configurados.

        Args:
            image_base64 (str): Imagen del reporte en base64
            title (str): Título del reporte que se incluirá en el mensaje

        Returns:
            dict: Resultado del envío con estadísticas
        """
        results = {
            'success': [],
            'failed': [],
            'total_numbers': 0,
            'message': '',
            'image_url': None
        }

        try:
            # Subir imagen a S3
            print("📤 Subiendo imagen a S3...")
            image_url = self.upload_base64_image_to_s3(image_base64, "sales_report")
            
            if not image_url:
                results['message'] = 'Error al subir la imagen a S3'
                return results

            results['image_url'] = image_url

            # Construir mensaje de texto
            message_text = f"📊 *{title}*\n\n"
            message_text += "Este es un reporte automático de ventas."

            # Obtener números de teléfono configurados para SALES_REPORT
            phone_numbers = EmailNotification.get_numbers_by_type_constant(
                notification_type_constant=EmailNotificationType.SALES_REPORT
            )
            phone_numbers = list(phone_numbers)

            results['total_numbers'] = len(phone_numbers)

            if not phone_numbers:
                results['message'] = 'No hay números de teléfono configurados para reportes de ventas'
                print(f"⚠️ {results['message']}")
                return results

            print(f"📱 Enviando reporte de ventas a {len(phone_numbers)} números...")

            # Enviar mensaje a cada número con delay entre envíos
            for idx, phone_number in enumerate(phone_numbers):
                try:
                    response_data, response = self.whatsapp_service.send_message(
                        to=phone_number,
                        text=message_text,
                        image=image_url
                    )

                    if response.status_code == 200:
                        results['success'].append(phone_number)
                        print(f"   ✅ Enviado exitosamente a {phone_number}")
                    else:
                        results['failed'].append({
                            'number': phone_number,
                            'error': str(response_data)
                        })
                        print(f"   ❌ Error al enviar a {phone_number}: {response_data}")

                except Exception as e:
                    results['failed'].append({
                        'number': phone_number,
                        'error': str(e)
                    })
                    print(f"   ❌ Excepción al enviar a {phone_number}: {e}")
                
                # Delay de 5 segundos entre envíos (excepto después del último)
                if idx < len(phone_numbers) - 1:
                    print(f"   ⏳ Esperando 5 segundos antes del siguiente envío...")
                    time.sleep(5)

            # Construir mensaje de resultado
            if results['success']:
                results['message'] = f"Reporte enviado exitosamente a {len(results['success'])} de {results['total_numbers']} números"
            else:
                results['message'] = 'No se pudo enviar el reporte a ningún número'

            print(f"📊 Resultado: {results['message']}")

        except Exception as e:
            results['message'] = f'Error general al enviar reporte: {str(e)}'
            print(f"❌ {results['message']}")

        return results

    def send_sales_report_with_custom_message(
        self, 
        image_base64: str, 
        title: str, 
        custom_message: str = None,
        include_timestamp: bool = True
    ) -> dict:
        """
        Envía un reporte de ventas por WhatsApp con mensaje personalizado.

        Args:
            image_base64 (str): Imagen del reporte en base64
            title (str): Título del reporte
            custom_message (str): Mensaje personalizado adicional (opcional)
            include_timestamp (bool): Si se incluye la fecha/hora del envío

        Returns:
            dict: Resultado del envío con estadísticas
        """
        results = {
            'success': [],
            'failed': [],
            'total_numbers': 0,
            'message': '',
            'image_url': None
        }

        try:
            # Subir imagen a S3
            print("📤 Subiendo imagen a S3...")
            image_url = self.upload_base64_image_to_s3(image_base64, "sales_report")
            
            if not image_url:
                results['message'] = 'Error al subir la imagen a S3'
                return results

            results['image_url'] = image_url

            # Construir mensaje de texto
            message_text = f"📊 *{title}*\n"
            
            if include_timestamp:
                timestamp = datetime.now().strftime('%d/%m/%Y %H:%M')
                message_text += f"📅 {timestamp}\n"
            
            message_text += "\n"
            
            if custom_message:
                message_text += f"{custom_message}\n"

            # Obtener números de teléfono configurados para SALES_REPORT
            phone_numbers = EmailNotification.get_numbers_by_type_constant(
                notification_type_constant=EmailNotificationType.SALES_REPORT
            )
            phone_numbers = list(phone_numbers)

            results['total_numbers'] = len(phone_numbers)

            if not phone_numbers:
                results['message'] = 'No hay números de teléfono configurados para reportes de ventas'
                print(f"⚠️ {results['message']}")
                return results

            print(f"📱 Enviando reporte de ventas personalizado a {len(phone_numbers)} números...")

            # Enviar mensaje a cada número con delay entre envíos
            for idx, phone_number in enumerate(phone_numbers):
                try:
                    response_data, response = self.whatsapp_service.send_message(
                        to=phone_number,
                        text=message_text,
                        image=image_url
                    )

                    if response.status_code == 200:
                        results['success'].append(phone_number)
                        print(f"   ✅ Enviado exitosamente a {phone_number}")
                    else:
                        results['failed'].append({
                            'number': phone_number,
                            'error': str(response_data)
                        })
                        print(f"   ❌ Error al enviar a {phone_number}: {response_data}")

                except Exception as e:
                    results['failed'].append({
                        'number': phone_number,
                        'error': str(e)
                    })
                    print(f"   ❌ Excepción al enviar a {phone_number}: {e}")
                
                # Delay de 5 segundos entre envíos (excepto después del último)
                if idx < len(phone_numbers) - 1:
                    print(f"   ⏳ Esperando 5 segundos antes del siguiente envío...")
                    time.sleep(5)

            # Construir mensaje de resultado
            if results['success']:
                results['message'] = f"Reporte enviado exitosamente a {len(results['success'])} de {results['total_numbers']} números"
            else:
                results['message'] = 'No se pudo enviar el reporte a ningún número'

            print(f"📊 Resultado: {results['message']}")

        except Exception as e:
            results['message'] = f'Error general al enviar reporte: {str(e)}'
            print(f"❌ {results['message']}")

        return results
