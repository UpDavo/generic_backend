from datetime import datetime
from django.conf import settings
import requests


BRAZE_API_URL = settings.BRAZE_URL
BRAZE_KEY = settings.BRAZE_KEY


class BrazeService:

    # constructor
    def __init__(self):
        self.headers = {
            "Authorization": f"Bearer {BRAZE_KEY}",
            "Content-Type": "application/json"
        }

    @staticmethod
    def get_most_recent_external_id(users):
        valid_users = []

        for user in users:
            apps = user.get("apps", [])
            if not apps:
                continue

            try:
                latest_app = max(
                    apps, key=lambda app: app.get("last_used", ""))
                last_used_dt = datetime.fromisoformat(
                    latest_app["last_used"].replace("Z", "+00:00"))
                valid_users.append((user, last_used_dt))
            except (ValueError, KeyError):
                continue

        if not valid_users:
            raise ValueError("No se encontraron usuarios con apps activas.")

        most_recent_user = max(valid_users, key=lambda item: item[1])[0]
        external_id = most_recent_user.get("external_id")

        if not external_id:
            raise ValueError(
                "El usuario con apps más recientes tiene cuenta duplicada.")

        return external_id

    def get_external_ids(self, email):

        user_data_payload = {
            "email_address": email,
            "fields_to_export": [
                "first_name",
                "phone",
                "braze_id",
                "external_id",
                "user_aliases",
                "apps"
            ]
        }
        user_response = requests.post(
            f"{BRAZE_API_URL}/users/export/ids", json=user_data_payload, headers=self.headers)
        user_response_data = user_response.json()
        return user_response_data

    def send_push_notification(self, external_id, message_title, message_text):
        # Enviar mensaje push
        message_payload = {
            "external_user_ids": [external_id],
            "messages": {
                "apple_push": {
                    "alert": {"title": message_title, "body": message_text},
                    "sound": "default",
                    "badge": 1,
                    "content-available": True
                },
                "android_push": {
                    "alert": message_text,
                    "title": message_title,
                    "sound": "default",
                    "priority": "high",
                    "notification_channel": "default_channel"
                }
            }
        }

        message_response = requests.post(
            f"{BRAZE_API_URL}/messages/send", json=message_payload, headers=self.headers)
        message_response_data = message_response.json()
        return message_response_data, message_response

    def send_massive_push_notification(self, external_ids, message_title, message_text):

        message_payload = {
            "external_user_ids": external_ids,
            "messages": {
                "apple_push": {
                    "alert": {"title": message_title, "body": message_text},
                    "sound": "default",
                    "badge": 1,
                    "content-available": True
                },
                "android_push": {
                    "alert": message_text,
                    "title": message_title,
                    "sound": "default",
                    "priority": "high",
                    "notification_channel": "default_channel"
                }
            }
        }

        message_response = requests.post(
            f"{BRAZE_API_URL}/campaigns/trigger/send", json=message_payload, headers=self.headers)
        message_response_data = message_response.json()
        return message_response_data, message_response

    def send_campaign(self, campaign_id, external_id):
        # Enviar mensaje push
        message_payload = {
            "campaign_id": campaign_id,
            "broadcast": False,
            "recipients": [
                {
                    "external_user_id": external_id,
                }
            ],
        }

        message_response = requests.post(
            f"{BRAZE_API_URL}/campaigns/trigger/send", json=message_payload, headers=self.headers)
        message_response_data = message_response.json()
        return message_response_data, message_response

    def send_massive_campaign(self, campaign_id, external_ids):
        # Enviar mensaje push
        message_payload = {
            "campaign_id": campaign_id,
            "broadcast": False,
            "recipients": [
                {
                    "external_user_id": external_id,
                } for external_id in external_ids
            ],
        }

        message_response = requests.post(
            f"{BRAZE_API_URL}/campaigns/trigger/send", json=message_payload, headers=self.headers)
        message_response_data = message_response.json()
        return message_response_data, message_response
