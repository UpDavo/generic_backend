from datetime import datetime
from django.conf import settings
import requests


WASENDER_URL = settings.WASENDER_URL
WASENDER_KEY = settings.WASENDER_KEY


class WhatsAppService:

    # constructor
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {WASENDER_KEY}",
            "Content-Type": "application/json"
        }

    def send_message(self, to, text, image=None):
        # Enviar mensaje push
        message_payload = {
            "to": to,
            "text": text
        }
        
        # Solo agregar imageUrl si se proporciona una imagen
        if image:
            message_payload["imageUrl"] = image

        message_response = requests.post(
            f"{WASENDER_URL}/send-message", json=message_payload, headers=self.headers)
        message_response_data = message_response.json()
        return message_response_data, message_response


