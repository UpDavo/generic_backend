from cryptography.fernet import Fernet
from django.conf import settings
import base64
import hashlib


class EncryptionService:
    """Servicio para encriptar y desencriptar datos sensibles"""

    @staticmethod
    def _get_key():
        """
        Genera una clave Fernet a partir del SECRET_KEY de Django.
        La clave Fernet debe ser de 32 bytes en base64.
        """
        # Usar el SECRET_KEY de Django como base
        secret = settings.SECRET_KEY.encode()
        # Generar un hash SHA256 (32 bytes)
        key_bytes = hashlib.sha256(secret).digest()
        # Codificar en base64 para Fernet
        key = base64.urlsafe_b64encode(key_bytes)
        return key

    @staticmethod
    def encrypt_data(data):
        """
        Encripta un diccionario/objeto Python.
        
        Args:
            data: Diccionario o datos serializables a JSON
            
        Returns:
            str: Datos encriptados en formato string
        """
        try:
            import json
            key = EncryptionService._get_key()
            fernet = Fernet(key)
            
            # Convertir datos a JSON string
            json_data = json.dumps(data)
            
            # Encriptar
            encrypted = fernet.encrypt(json_data.encode())
            
            # Retornar como string base64
            return encrypted.decode()
        except Exception as e:
            print(f"Error al encriptar datos: {e}")
            return None

    @staticmethod
    def decrypt_data(encrypted_data):
        """
        Desencripta datos previamente encriptados.
        
        Args:
            encrypted_data: String con datos encriptados
            
        Returns:
            dict: Diccionario con los datos desencriptados
        """
        try:
            import json
            key = EncryptionService._get_key()
            fernet = Fernet(key)
            
            # Desencriptar
            decrypted = fernet.decrypt(encrypted_data.encode())
            
            # Convertir de JSON a dict
            data = json.loads(decrypted.decode())
            
            return data
        except Exception as e:
            print(f"Error al desencriptar datos: {e}")
            return None
