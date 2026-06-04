"""
WaqaaClient — talks to the waqaa verification API.

Auth: X-API-Key header (set in settings.WAQAA_ORG_API_KEY).
Base URL: settings.WAQAA_BASE_URL (e.g. http://192.168.8.97:8000).

This client matches the actual waqaa contract:
  - POST /api/verification/sessions/create/
    Body: {external_user_ref, org_operation_ref, operation_type, operation_hash?, operation_payload_encrypted?}
    Response: {session_id, challenge_bytes, challenge_expires_at, session_status, session}

  - GET /api/verification/sessions/<id>/status/
    Response: {id, status, ...}
    status values: pending, challenge_issued, verified, denied, failed, expired, cancelled

  - POST /api/verification/sessions/<id>/cancel/
    Response: session details

  - POST /api/verification/sessions/<id>/verify-token/
    Body: {decision_token}
    Response: {valid: bool}
"""
import hashlib
import json

import requests
from django.conf import settings


class WaqaaClient:
    BASE_URL = settings.WAQAA_BASE_URL.rstrip("/")
    API_KEY = settings.WAQAA_ORG_API_KEY
    TIMEOUT = 10

    # ───────────────────────────────
    # Headers
    # ───────────────────────────────
    @staticmethod
    def _headers():
        return {
            "Content-Type": "application/json",
            "X-API-Key": WaqaaClient.API_KEY,
        }

    # ───────────────────────────────
    # Helper: build deterministic operation_hash
    # ───────────────────────────────
    @staticmethod
    def build_operation_hash(*, amount, from_account, to_account, txn_id):
        """
        Build a SHA-256 hash binding the operation to a specific intent.
        Same inputs always produce the same hash → tamper-evident.
        """
        payload = f"{txn_id}|{from_account}|{to_account}|{amount}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    # ───────────────────────────────
    # Helper: build human-readable payload for mobile display
    # ───────────────────────────────
    @staticmethod
    def build_operation_payload(*, amount, from_account, to_account, description=""):
        """
        For demo: send a plain JSON describing the operation so the
        mobile app can display it. In production, this should be
        encrypted with a per-user key the mobile already has.
        """
        return json.dumps({
            "amount": str(amount),
            "from_account": from_account,
            "to_account": to_account,
            "description": description or "تحويل",
            "currency": "SAR",
        }, ensure_ascii=False)

    # ───────────────────────────────
    # Create a verification session
    # ───────────────────────────────
    @staticmethod
    def create_session(
        *,
        external_user_ref: str,
        org_operation_ref: str,
        operation_type: str,
        operation_hash: str = None,
        operation_payload: str = None,
    ) -> dict:
        """
        Create a new verification session in waqaa.

        Args:
            external_user_ref: Stable user ID known to both systems
                              (we use the waqaa AccountUser UUID).
            org_operation_ref: Unique per-org reference (we use Transaction.id).
            operation_type: One of waqaa's OperationType values
                            (e.g. 'transfer', 'payment', 'login').
            operation_hash: SHA-256 hex of operation details (use build_operation_hash).
            operation_payload: Display payload for the mobile app
                              (use build_operation_payload).

        Returns:
            {
                "session_id": "<uuid>",
                "challenge_bytes": "<hex>",
                "challenge_expires_at": "<iso datetime>",
                "session_status": "challenge_issued",
                "session": {...},
            }

        Raises:
            Exception with the waqaa error detail on failure.
        """
        if operation_type == "transfer" and not org_operation_ref.startswith("txn_"):
             org_operation_ref = f"txn_{org_operation_ref}"
        body = {
            "external_user_ref": external_user_ref,
            "org_operation_ref": org_operation_ref,
            "operation_type": operation_type,
        }
        if operation_hash:
            body["operation_hash"] = operation_hash
        if operation_payload:
            body["operation_payload_encrypted"] = operation_payload

        try:
            response = requests.post(
                f"{WaqaaClient.BASE_URL}/api/verification/sessions/create/",
                json=body,
                headers=WaqaaClient._headers(),
                timeout=WaqaaClient.TIMEOUT,
            )
        except requests.RequestException as exc:
            raise Exception(f"Network error calling waqaa: {exc}")

        if response.status_code != 201:
            try:
                detail = response.json().get("detail", response.text[:200])
            except Exception:
                detail = response.text[:200]
            raise Exception(f"waqaa create_session failed [{response.status_code}]: {detail}")

        return response.json()

    # ───────────────────────────────
    # Get session status (used by polling)
    # ───────────────────────────────
    @staticmethod
    def get_session_status(session_id: str) -> dict:
        """
        Returns:
            {
                "id": "<uuid>",
                "status": "challenge_issued" | "verified" | "denied" | ...,
                ...
            }
        """
        try:
            response = requests.get(
                f"{WaqaaClient.BASE_URL}/api/verification/sessions/{session_id}/status/",
                headers=WaqaaClient._headers(),
                timeout=WaqaaClient.TIMEOUT,
            )
        except requests.RequestException as exc:
            raise Exception(f"Network error calling waqaa: {exc}")

        if response.status_code != 200:
            raise Exception(
                f"waqaa get_session_status failed [{response.status_code}]: {response.text[:200]}"
            )

        return response.json()

    # ───────────────────────────────
    # Cancel a session (timeout / user abort)
    # ───────────────────────────────
    @staticmethod
    def cancel_session(session_id: str) -> dict:
        try:
            response = requests.post(
                f"{WaqaaClient.BASE_URL}/api/verification/sessions/{session_id}/cancel/",
                headers=WaqaaClient._headers(),
                timeout=WaqaaClient.TIMEOUT,
            )
        except requests.RequestException as exc:
            raise Exception(f"Network error calling waqaa: {exc}")

        if response.status_code not in (200, 409):
            raise Exception(
                f"waqaa cancel_session failed [{response.status_code}]: {response.text[:200]}"
            )

        return response.json() if response.status_code == 200 else {}