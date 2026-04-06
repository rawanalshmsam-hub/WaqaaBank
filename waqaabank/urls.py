from django.urls import path

# Auth
from .views.auth_views import login_view, logout_view

# Dashboard
from .views.dashboard_views import dashboard_view

# Transfers
from .views.transfer_views import (
    transfer_view,
    verify_view,
    transfer_status,
)


urlpatterns = [


    # ─────────────── Auth ───────────────
    path('', login_view, name='login'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),

    # ───────────── Dashboard ─────────────
    path('dashboard/', dashboard_view, name='dashboard'),

    # ───────────── Transfers ─────────────
    path('transfer/', transfer_view, name='transfer'),

    # Verification flow
    path('transfer/verify/<uuid:txn_id>/', verify_view, name='verify'),

    # Polling endpoint (AJAX)
    path('transfer/status/<uuid:txn_id>/', transfer_status, name='transfer_status'),
]