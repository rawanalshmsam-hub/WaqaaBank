from django.shortcuts import render, redirect
from django.contrib.auth.hashers import make_password

from ..models import Client
from ..utils.hash_utils import (
    hash_national_id,
    hash_phone,
)


def register_view(request):

    if request.method == "GET":
        return render(request, "register.html")

    full_name = request.POST.get("full_name", "").strip()
    national_id = request.POST.get("national_id", "").strip()
    phone = request.POST.get("phone", "").strip()
    email = request.POST.get("email", "").strip()
    username = request.POST.get("username", "").strip()
    password = request.POST.get("password", "").strip()

    try:
        Client.objects.create(
            full_name=full_name,
            national_id_hmac=hash_national_id(national_id),
            phone_hmac=hash_phone(phone),
            email_hmac=email,
            username=username,
            password_hash=make_password(password),
            status="active",
            kyc_verified=True,
        )

        return redirect("login")

    except Exception as e:
        return render(
            request,
            "register.html",
            {"error": str(e)},
        )