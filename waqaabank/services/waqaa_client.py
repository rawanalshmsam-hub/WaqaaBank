import requests
from django.conf import settings


class WaqaaClient:
    BASE_URL = settings.WAQAA_BASE_URL
    API_KEY  = settings.WAQAA_ORG_API_KEY
    TIMEOUT  = 10

    @staticmethod
    def _headers():
        return {
            "Content-Type": "application/json",
        }

    # ───────────────────────────────
    # إنشاء جلسة تحقق
    # ───────────────────────────────
    @staticmethod
    def create_session(external_user_ref: str, org_operation_ref: str, operation_type: str) -> dict:
        try:
            response = requests.post(
                f"{WaqaaClient.BASE_URL}/api/sessions/",
                json={
                    "organization_api_key": WaqaaClient.API_KEY,
                    "external_user_ref": external_user_ref,
                    "org_operation_ref": org_operation_ref,
                    "operation_type": operation_type,
                },
                headers=WaqaaClient._headers(),
                timeout=WaqaaClient.TIMEOUT,
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise Exception(f"Waqaa create_session failed: {str(e)}")

    # ───────────────────────────────
    # جلب حالة الجلسة
    # ───────────────────────────────
    @staticmethod
    def get_session_status(session_id: str) -> dict:
        try:
            response = requests.get(
                f"{WaqaaClient.BASE_URL}/api/sessions/{session_id}/",
                headers=WaqaaClient._headers(),
                timeout=WaqaaClient.TIMEOUT,
            )

            response.raise_for_status()
            return response.json()

        except requests.RequestException as e:
            raise Exception(f"Waqaa get_session_status failed: {str(e)}")