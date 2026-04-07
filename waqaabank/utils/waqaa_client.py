import requests
from django.conf import settings


class WaqaaClient:
    TIMEOUT = 10

    @staticmethod
    def create_session(external_user_ref: str, org_operation_ref: str, operation_type: str) -> dict:
        response = requests.post(
            f"{settings.WAQAA_BASE_URL}/api/sessions/",
            json={
                "organization_api_key": settings.WAQAA_ORG_API_KEY,
                "external_user_ref": external_user_ref,
                "org_operation_ref": org_operation_ref,
                "operation_type": operation_type,
            },
            timeout=WaqaaClient.TIMEOUT
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def get_session_status(session_id: str) -> dict:
        response = requests.get(
            f"{settings.WAQAA_BASE_URL}/api/sessions/{session_id}/",
            timeout=WaqaaClient.TIMEOUT
        )
        response.raise_for_status()
        return response.json()