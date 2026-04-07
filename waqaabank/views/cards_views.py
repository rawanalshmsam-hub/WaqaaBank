from django.shortcuts import render, redirect
from ..models import Account, Card

def cards_view(request):
    if not request.session.get('client_id'):
        return redirect('login')
    
    client_id = request.session['client_id']
    
    cards = Card.objects.filter(
        account__client_id=client_id
    ).select_related('account')
    
    return render(request, 'cards.html', {
        'cards': cards,
    })