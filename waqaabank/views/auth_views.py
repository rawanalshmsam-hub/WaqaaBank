from datetime import timedelta
from django.shortcuts import render, redirect
from django.utils import timezone
from django.contrib.auth.hashers import check_password
from ..models import Client, BankAuditLog, LoginSession


def get_client_ip(request):
    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded:
        return x_forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_audit(client_id, action, result, ip_address=None, failure_reason=None, user_agent=None, metadata=None):
    BankAuditLog.objects.create(
        client_id=client_id,
        action=action,
        result=result,
        ip_address=ip_address,
        failure_reason=failure_reason,
        user_agent=user_agent,
        metadata=metadata,
    )


def login_view(request):
    if request.session.get('client_id'):
        return redirect('dashboard')

    if request.method == 'GET':
        return render(request, 'login.html')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '').strip()
        ip = get_client_ip(request)
        user_agent = request.META.get('HTTP_USER_AGENT', '')

        if not username or not password:
            return render(request, 'login.html', {
                'error': 'فضلاً أدخل اسم المستخدم وكلمة المرور'
            })

        try:
            client = Client.objects.get(username=username)
        except Client.DoesNotExist:
            log_audit(
                client_id=None,
                action='login',
                result='fail',
                ip_address=ip,
                failure_reason='username_not_found',
                user_agent=user_agent,
            )
            return render(request, 'login.html', {
                'error': 'اسم المستخدم أو كلمة المرور غلط'
            })

        if client.locked_until and client.locked_until > timezone.now():
            remaining = max(1, int((client.locked_until - timezone.now()).total_seconds() / 60))

            log_audit(
                client_id=client.id,
                action='login',
                result='fail',
                ip_address=ip,
                failure_reason='login_attempt_while_locked',
                user_agent=user_agent,
            )

            return render(request, 'login.html', {
                'error': f'الحساب مقفول. حاول بعد {remaining} دقيقة'
            })

        if client.status in ['suspended', 'closed']:
            log_audit(
                client_id=client.id,
                action='login',
                result='fail',
                ip_address=ip,
                failure_reason='account_inactive',
                user_agent=user_agent,
            )
            return render(request, 'login.html', {
                'error': 'هذا الحساب موقوف. تواصل مع الدعم'
            })

        if not check_password(password, client.password_hash):
            client.failed_login_attempts += 1

            if client.failed_login_attempts >= 5:
                client.locked_until = timezone.now() + timedelta(minutes=15)
                client.failed_login_attempts = 0
                client.save(update_fields=['locked_until', 'failed_login_attempts', 'updated_at'])

                log_audit(
                    client_id=client.id,
                    action='login',
                    result='fail',
                    ip_address=ip,
                    failure_reason='account_locked',
                    user_agent=user_agent,
                )

                return render(request, 'login.html', {
                    'error': 'تم قفل حسابك 15 دقيقة بسبب محاولات متعددة'
                })

            client.save(update_fields=['failed_login_attempts', 'updated_at'])

            log_audit(
                client_id=client.id,
                action='login',
                result='fail',
                ip_address=ip,
                failure_reason='wrong_password',
                user_agent=user_agent,
            )

            return render(request, 'login.html', {
                'error': f'كلمة المرور غلط. تبقى {5 - client.failed_login_attempts} محاولات'
            })

        client.failed_login_attempts = 0
        client.last_login_at = timezone.now()
        client.last_login_ip = ip
        client.locked_until = None
        client.save(update_fields=[
            'failed_login_attempts',
            'last_login_at',
            'last_login_ip',
            'locked_until',
            'updated_at',
        ])

        log_audit(
            client_id=client.id,
            action='login',
            result='ok',
            ip_address=ip,
            failure_reason=None,
            user_agent=user_agent,
        )

        request.session['client_id'] = str(client.id)
        request.session['client_name'] = client.full_name
        request.session.set_expiry(1800)

        return redirect('dashboard')

    return render(request, 'login.html')


def logout_view(request):
    client_id = request.session.get('client_id')
    ip = get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if client_id:
        log_audit(
            client_id=client_id,
            action='logout',
            result='ok',
            ip_address=ip,
            failure_reason=None,
            user_agent=user_agent,
        )

    request.session.flush()
    return redirect('login')