"""
Link waqaa view — handles linking a waqaabank Client to their waqaa AccountUser.

The user provides their national_id (the same one they used in waqaa).
waqaabank computes plain SHA-256 of it (NOT with the bank's pepper)
and sends it to waqaa. Waqaa then applies its own pepper to find the user.
"""
import hashlib
import requests
from django.conf import settings
from django.shortcuts import render, redirect
from django.utils import timezone

from ..models import Client


def link_waqaa_view(request):
    # ─── Check session ───
    client_id = request.session.get("client_id")
    if not client_id:
        return redirect("login")

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return redirect("login")

    # ─── Already linked? ───
    if client.waqaa_user_id:
        return render(request, "link_waqaa.html", {
            "client": client,
            "success": True,
            "already_linked": True,
        })

    # ─── GET: show form ───
    if request.method == "GET":
        return render(request, "link_waqaa.html", {
            "client": client,
        })

    # ─── POST: process the link ───
    national_id = (request.POST.get("national_id") or "").strip()

    # Basic validation
    if not national_id or not national_id.isdigit() or len(national_id) != 10:
        return render(request, "link_waqaa.html", {
            "client": client,
            "error": "رقم الهوية يجب أن يكون 10 أرقام",
        })

    # ⭐ Compute plain SHA-256 of the national_id
    # (waqaa will apply its own pepper after receiving this)
    national_id_sha256 = hashlib.sha256(national_id.encode("utf-8")).hexdigest()

    print(f"\n🔗 LINK WAQAA")
    print(f"   national_id (entered): {national_id[:3]}***{national_id[-2:]}")
    print(f"   SHA-256: {national_id_sha256[:16]}...")
    print(f"   WAQAA_BASE_URL: {settings.WAQAA_BASE_URL}")

    try:
        response = requests.post(
            f"{settings.WAQAA_BASE_URL}/api/organization/links/",
            headers={
                "X-API-Key": settings.WAQAA_ORG_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "national_id_hash": national_id_sha256,
                "external_provider": "internal",
                "external_user_ref": str(client.id),
                "role": "member",
            },
            timeout=10,
        )

        print(f"   STATUS: {response.status_code}")
        print(f"   BODY: {response.text[:300]}\n")

        # ─── Success ───
        if response.status_code == 201:
            data = response.json()

            # The response contains the link's id and user_id
            waqaa_user_id = data.get("user_id") or data.get("user")

            if not waqaa_user_id:
                return render(request, "link_waqaa.html", {
                    "client": client,
                    "error": "تم الربط لكن لم نستلم معرّف وقاء. تواصلي مع الدعم.",
                })

            client.waqaa_user_id = waqaa_user_id
            client.waqaa_linked_at = timezone.now()
            client.save(update_fields=["waqaa_user_id", "waqaa_linked_at"])

            return render(request, "link_waqaa.html", {
                "client": client,
                "success": True,
            })

        # ─── Already linked (409) ───
        if response.status_code == 409:
            return render(request, "link_waqaa.html", {
                "client": client,
                "error": "هذا الحساب مربوط بالفعل بمؤسسة وقاء. تواصلي مع الدعم.",
            })

        # ─── User not found in waqaa (404) ───
        if response.status_code == 404:
            return render(request, "link_waqaa.html", {
                "client": client,
                "error": (
                    "لا يوجد حساب نشط في وقاء بهذا الرقم. "
                    "تأكدي من إنشاء حساب في تطبيق وقاء أولاً."
                ),
            })

        # ─── Other errors ───
        return render(request, "link_waqaa.html", {
            "client": client,
            "error": f"فشل الربط ({response.status_code}). حاولي لاحقاً.",
        })

    except requests.RequestException as e:
        print(f"   ❌ Network error: {e}")
        return render(request, "link_waqaa.html", {
            "client": client,
            "error": "تعذّر الاتصال بخدمة وقاء. تأكدي من تشغيل الخادم.",
        })

    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        import traceback
        print(traceback.format_exc())
        return render(request, "link_waqaa.html", {
            "client": client,
            "error": "حدث خطأ غير متوقّع. حاولي لاحقاً.",
        })