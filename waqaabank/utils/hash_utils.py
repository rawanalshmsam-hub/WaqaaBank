import hmac
import hashlib
from django.conf import settings


def hash_national_id(national_id: str) -> str:
    return hmac.new(
        settings.NATIONAL_ID_HMAC_SECRET.encode(),
        f"national_id:{national_id}".encode(),
        hashlib.sha256
    ).hexdigest()


def hash_phone(phone: str) -> str:
    return hmac.new(
        settings.PHONE_HMAC_SECRET.encode(),
        f"phone:{phone}".encode(),
        hashlib.sha256
    ).hexdigest()