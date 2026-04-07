from django.shortcuts import render, redirect
from ..models import Account, Bill

def bills_view(request):
    if not request.session.get('client_id'):
        return redirect('login')
    
    client_id = request.session['client_id']
    
    bills = Bill.objects.filter(
        client_id=client_id
    ).select_related('account').order_by('-created_at')
    
    return render(request, 'bills.html', {
        'bills': bills,
    })