from django.shortcuts import render, redirect
from django.db.models import Q, Sum
from ..models import Client, Account, Transaction


def dashboard_view(request):
    if not request.session.get('client_id'):
        return redirect('login')

    client_id = request.session['client_id']

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        request.session.flush()
        return redirect('login')

    if client.status != 'active':
        request.session.flush()
        return redirect('login')

    accounts = Account.objects.filter(
        client=client,
        status='active'
    ).order_by('-created_at')

    account_ids = list(accounts.values_list('id', flat=True))

    transactions = Transaction.objects.filter(
        Q(from_account_id__in=account_ids) | Q(to_account_id__in=account_ids)
    ).select_related(
        'from_account',
        'to_account'
    ).order_by('-created_at')[:10]

    total_balance = accounts.aggregate(total=Sum('balance'))['total'] or 0

    return render(request, 'dashboard.html', {
        'client': client,
        'accounts': accounts,
        'transactions': transactions,
        'total_balance': total_balance,
    })