import uuid
from decimal import Decimal, InvalidOperation
from datetime import timedelta

from django.shortcuts import render, redirect
from django.utils import timezone
from django.http import JsonResponse
from django.db import transaction

from ..models import Client, Account, Transaction

from ..services.waqaa_client import WaqaaClient

from ..utils.hash_utils import hash_phone

from .auth_views import get_client_ip, log_audit


TRANSFER_EXPIRY_MINUTES = 10


def _reset_daily_spent_if_needed(account: Account) -> None:
    now = timezone.now()

    if (
        account.daily_spent_reset_at is None
        or account.daily_spent_reset_at.date() < now.date()
    ):
        account.daily_spent = Decimal('0.00')
        account.daily_spent_reset_at = now


def _get_logged_in_client(request):
    client_id = request.session.get('client_id')
    if not client_id:
        return None

    try:
        return Client.objects.get(id=client_id, status='active')
    except Client.DoesNotExist:
        request.session.flush()
        return None


def transfer_view(request):
    client = _get_logged_in_client(request)
    if not client:
        return redirect('login')

    accounts = Account.objects.filter(
        client=client,
        status='active'
    ).order_by('-created_at')

    if request.method == 'GET':
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
        })

    from_account_id = request.POST.get('from_account')
    to_account_number = request.POST.get('to_account_number', '').strip()
    amount_raw = request.POST.get('amount', '').strip()
    description = request.POST.get('description', '').strip()
    ip = get_client_ip(request)

    if not from_account_id or not to_account_number or not amount_raw:
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'فضلاً عبّي جميع الحقول المطلوبة'
        })

    try:
        from_account = Account.objects.get(
            id=from_account_id,
            client=client,
            status='active'
        )
    except Account.DoesNotExist:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'invalid_source_account'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'الحساب المرسل غير موجود أو غير نشط'
        })

    try:
        to_account = Account.objects.get(
            account_number=to_account_number,
            status='active'
        )
    except Account.DoesNotExist:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'invalid_destination_account'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'رقم الحساب المستلم غير موجود أو غير نشط'
        })

    if from_account.id == to_account.id:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'same_account_transfer'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'لا يمكن التحويل إلى نفس الحساب'
        })

    try:
        amount = Decimal(amount_raw)
        if amount <= Decimal('0.00'):
            raise InvalidOperation
    except (InvalidOperation, TypeError, ValueError):
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'invalid_amount'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'المبلغ غير صحيح'
        })

    _reset_daily_spent_if_needed(from_account)

    if from_account.balance < amount:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'insufficient_balance'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'الرصيد غير كافٍ'
        })

    if from_account.daily_spent + amount > from_account.daily_limit:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'daily_limit_exceeded'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': f'تجاوزت الحد اليومي ({from_account.daily_limit} ريال)'
        })

    if amount > from_account.single_limit:
        log_audit(
            client.id,
            'transfer_create',
            'fail',
            ip,
            'single_limit_exceeded'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': f'المبلغ يتجاوز حد العملية الواحدة ({from_account.single_limit} ريال)'
        })

    requires_waqaa = amount >= from_account.waqaa_threshold

    reference_number = f"TXN-{uuid.uuid4().hex[:10].upper()}"
    idempotency_key = f"{client.id}:{from_account.id}:{to_account.id}:{amount}:{timezone.now().date()}"

    existing_txn = Transaction.objects.filter(
        idempotency_key=idempotency_key,
        status__in=['pending', 'requires_verification', 'processing', 'completed']
    ).first()

    if existing_txn:
        if existing_txn.requires_waqaa and existing_txn.status in ['requires_verification', 'processing']:
            return redirect('verify', txn_id=existing_txn.id)

        if existing_txn.status == 'completed':
            return redirect('result_success', txn_id=existing_txn.id)

    txn = Transaction.objects.create(
        from_account=from_account,
        to_account=to_account,
        transaction_type='transfer',
        amount=amount,
        description=description,
        reference_number=reference_number,
        idempotency_key=idempotency_key,
        status='requires_verification' if requires_waqaa else 'processing',
        requires_waqaa=requires_waqaa,
        initiated_by_ip=ip,
        expires_at=timezone.now() + timedelta(minutes=TRANSFER_EXPIRY_MINUTES),
        waqaa_status='pending' if requires_waqaa else None,
    )

    log_audit(
        client.id,
        'transfer_create',
        'ok',
        ip,
        None
    )

    if requires_waqaa:
        if not client.waqaa_user_id:
            txn.status = 'failed'
            txn.failure_reason = 'waqaa_user_not_linked'
            txn.failed_at = timezone.now()
            txn.save(update_fields=['status', 'failure_reason', 'failed_at'])

            log_audit(
                client.id,
                'transfer_create',
                'fail',
                ip,
                'waqaa_user_not_linked'
            )
            return render(request, 'transfer.html', {
                'client': client,
                'accounts': accounts,
                'error': 'الحساب غير مرتبط بوقاء'
            })

        try:
            waqaa_response = WaqaaClient.create_session(
                external_user_ref=str(client.waqaa_user_id),
                org_operation_ref=str(txn.id),
                operation_type='transfer',
            )

            txn.waqaa_session_id = waqaa_response['session_id']
            txn.waqaa_status = 'pending'
            txn.save(update_fields=['waqaa_session_id', 'waqaa_status'])

            return redirect('verify', txn_id=txn.id)

        except Exception:
            txn.status = 'failed'
            txn.failure_reason = 'waqaa_session_creation_failed'
            txn.failed_at = timezone.now()
            txn.save(update_fields=['status', 'failure_reason', 'failed_at'])

            log_audit(
                client.id,
                'transfer_create',
                'fail',
                ip,
                'waqaa_session_creation_failed'
            )
            return render(request, 'transfer.html', {
                'client': client,
                'accounts': accounts,
                'error': 'فشل الاتصال بخدمة وقاء. حاول مرة ثانية'
            })

    try:
        with transaction.atomic():
            locked_from_account = Account.objects.select_for_update().get(
                id=from_account.id,
                client=client,
                status='active'
            )
            locked_to_account = Account.objects.select_for_update().get(
                id=to_account.id,
                status='active'
            )
            locked_txn = Transaction.objects.select_for_update().get(id=txn.id)

            _reset_daily_spent_if_needed(locked_from_account)

            if locked_from_account.balance < locked_txn.amount:
                locked_txn.status = 'failed'
                locked_txn.failure_reason = 'insufficient_balance_at_execution'
                locked_txn.failed_at = timezone.now()
                locked_txn.save(update_fields=['status', 'failure_reason', 'failed_at'])

                log_audit(
                    client.id,
                    'transfer_execute',
                    'fail',
                    ip,
                    'insufficient_balance_at_execution'
                )
                return render(request, 'transfer.html', {
                    'client': client,
                    'accounts': accounts,
                    'error': 'الرصيد لم يعد كافيًا لتنفيذ العملية'
                })

            if locked_from_account.daily_spent + locked_txn.amount > locked_from_account.daily_limit:
                locked_txn.status = 'failed'
                locked_txn.failure_reason = 'daily_limit_exceeded_at_execution'
                locked_txn.failed_at = timezone.now()
                locked_txn.save(update_fields=['status', 'failure_reason', 'failed_at'])

                log_audit(
                    client.id,
                    'transfer_execute',
                    'fail',
                    ip,
                    'daily_limit_exceeded_at_execution'
                )
                return render(request, 'transfer.html', {
                    'client': client,
                    'accounts': accounts,
                    'error': 'تم تجاوز الحد اليومي وقت التنفيذ'
                })

            locked_from_account.balance -= locked_txn.amount
            locked_from_account.daily_spent += locked_txn.amount
            locked_from_account.save(update_fields=['balance', 'daily_spent', 'daily_spent_reset_at', 'updated_at'])

            locked_to_account.balance += locked_txn.amount
            locked_to_account.save(update_fields=['balance', 'updated_at'])

            locked_txn.status = 'completed'
            locked_txn.completed_at = timezone.now()
            locked_txn.save(update_fields=['status', 'completed_at'])

        log_audit(client.id, 'transfer_completed', 'ok', ip, None)
        return redirect('result_success', txn_id=txn.id)

    except Exception:
        txn.status = 'failed'
        txn.failure_reason = 'execution_failed'
        txn.failed_at = timezone.now()
        txn.save(update_fields=['status', 'failure_reason', 'failed_at'])

        log_audit(
            client.id,
            'transfer_execute',
            'fail',
            ip,
            'execution_failed'
        )
        return render(request, 'transfer.html', {
            'client': client,
            'accounts': accounts,
            'error': 'فشل تنفيذ التحويل'
        })


def verify_view(request, txn_id):
    client = _get_logged_in_client(request)
    if not client:
        return redirect('login')

    try:
        txn = Transaction.objects.get(
            id=txn_id,
            from_account__client=client
        )
    except Transaction.DoesNotExist:
        return redirect('dashboard')

    return render(request, 'verify.html', {
        'client': client,
        'txn': txn,
    })


def transfer_status(request, txn_id):
    if not request.session.get('client_id'):
        return JsonResponse({'error': 'unauthorized'}, status=401)

    client = _get_logged_in_client(request)
    if not client:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    try:
        txn = Transaction.objects.get(
            id=txn_id,
            from_account__client=client
        )
    except Transaction.DoesNotExist:
        return JsonResponse({'error': 'not_found'}, status=404)

    if txn.status == 'completed':
        return JsonResponse({'status': 'verified'})

    if txn.status == 'failed':
        return JsonResponse({
            'status': 'failed',
            'reason': txn.failure_reason
        })

    if txn.expires_at and txn.expires_at < timezone.now():
        txn.status = 'failed'
        txn.waqaa_status = 'expired'
        txn.failure_reason = 'expired'
        txn.failed_at = timezone.now()
        txn.save(update_fields=['status', 'waqaa_status', 'failure_reason', 'failed_at'])

        log_audit(
            client.id,
            'transfer_verify',
            'fail',
            get_client_ip(request),
            'expired'
        )
        return JsonResponse({'status': 'expired'})

    if not txn.waqaa_session_id:
        return JsonResponse({'status': 'error', 'message': 'missing_waqaa_session'}, status=400)

    try:
        waqaa_response = WaqaaClient.get_session_status(str(txn.waqaa_session_id))
        waqaa_status = waqaa_response.get('status')

        if waqaa_status == 'verified':
            ip = get_client_ip(request)

            with transaction.atomic():
                locked_txn = Transaction.objects.select_for_update().get(
                    id=txn.id,
                    from_account__client=client
                )

                if locked_txn.status == 'completed':
                    return JsonResponse({'status': 'verified'})

                locked_from_account = Account.objects.select_for_update().get(
                    id=locked_txn.from_account_id,
                    client=client,
                    status='active'
                )
                locked_to_account = Account.objects.select_for_update().get(
                    id=locked_txn.to_account_id,
                    status='active'
                )

                _reset_daily_spent_if_needed(locked_from_account)

                if locked_from_account.balance < locked_txn.amount:
                    locked_txn.status = 'failed'
                    locked_txn.waqaa_status = 'verified'
                    locked_txn.failure_reason = 'insufficient_balance_at_execution'
                    locked_txn.failed_at = timezone.now()
                    locked_txn.save(update_fields=[
                        'status', 'waqaa_status', 'failure_reason', 'failed_at'
                    ])

                    log_audit(
                        client.id,
                        'transfer_execute',
                        'fail',
                        ip,
                        'insufficient_balance_at_execution'
                    )
                    return JsonResponse({'status': 'failed'})

                if locked_from_account.daily_spent + locked_txn.amount > locked_from_account.daily_limit:
                    locked_txn.status = 'failed'
                    locked_txn.waqaa_status = 'verified'
                    locked_txn.failure_reason = 'daily_limit_exceeded_at_execution'
                    locked_txn.failed_at = timezone.now()
                    locked_txn.save(update_fields=[
                        'status', 'waqaa_status', 'failure_reason', 'failed_at'
                    ])

                    log_audit(
                        client.id,
                        'transfer_execute',
                        'fail',
                        ip,
                        'daily_limit_exceeded_at_execution'
                    )
                    return JsonResponse({'status': 'failed'})

                locked_from_account.balance -= locked_txn.amount
                locked_from_account.daily_spent += locked_txn.amount
                locked_from_account.save(update_fields=['balance', 'daily_spent', 'daily_spent_reset_at', 'updated_at'])

                locked_to_account.balance += locked_txn.amount
                locked_to_account.save(update_fields=['balance', 'updated_at'])

                locked_txn.status = 'completed'
                locked_txn.waqaa_status = 'verified'
                locked_txn.waqaa_verified_at = timezone.now()
                locked_txn.completed_at = timezone.now()
                locked_txn.save(update_fields=[
                    'status',
                    'waqaa_status',
                    'waqaa_verified_at',
                    'completed_at'
                ])

            log_audit(client.id, 'transfer_completed', 'ok', ip, None)
            return JsonResponse({'status': 'verified'})

        if waqaa_status in ['failed', 'expired', 'cancelled']:
            txn.status = 'failed'
            txn.waqaa_status = waqaa_status
            txn.failure_reason = waqaa_status
            txn.failed_at = timezone.now()
            txn.save(update_fields=['status', 'waqaa_status', 'failure_reason', 'failed_at'])

            log_audit(
                client.id,
                'transfer_verify',
                'fail',
                get_client_ip(request),
                waqaa_status
            )
            return JsonResponse({'status': 'failed'})

        txn.waqaa_status = 'pending'
        txn.save(update_fields=['waqaa_status'])
        return JsonResponse({'status': 'pending'})

    except Exception:
        return JsonResponse({
            'status': 'error',
            'message': 'waqaa_status_check_failed'
        }, status=500)