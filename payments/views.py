import uuid
import requests
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from datetime import timedelta
from lendogo.models import Listing

@login_required
def boost_listing(request, listing_id):
    """
    User clicks 'Boost for MK 500' → creates PayChangu checkout
    """
    listing = get_object_or_404(Listing, id=listing_id, seller=request.user)

    tx_ref = f"boost_{listing.id}_{uuid.uuid4().hex[:8]}"
    
    # Save tx_ref BEFORE hitting PayChangu so webhook can match it
    listing.boost_tx_ref = tx_ref
    listing.save(update_fields=['boost_tx_ref'])

    payload = {
        "amount": 500,
        "currency": "MWK",
        "email": request.user.email,
        "first_name": request.user.first_name or request.user.username,
        "last_name": request.user.last_name or "",
        "callback_url": request.build_absolute_uri('/payments/webhook/'),
        "return_url": request.build_absolute_uri('/payments/verify/'),
        "tx_ref": tx_ref,
        "customization": {
            "title": "Lendogo Boost",
            "description": f"7-day boost for {listing.product}"
        },
        "meta": {
            "listing_id": listing.id,
            "user_id": request.user.id
        }
    }

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {settings.PAYCHANGU_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post("https://api.paychangu.com/payment", json=payload, headers=headers)
        data = response.json()

        if response.status_code in [200, 201] and data.get('status') == 'success':
            checkout_url = data['data']['checkout_url']
            return redirect(checkout_url)
        else:
            return JsonResponse({
                "error": "Payment initialization failed",
                "details": data.get('message', response.text)
            }, status=400)

    except Exception as e:
        return JsonResponse({"error": "Request failed", "details": str(e)}, status=500)


def verify_payment(request):
    """
    User gets redirected here after PayChangu checkout
    This is the return_url - handles success/fail UI
    """
    tx_ref = request.GET.get('tx_ref')
    status = request.GET.get('status')

    if status == 'success' and tx_ref and tx_ref.startswith('boost_'):
        try:
            listing_id = int(tx_ref.split('_')[1])
            listing = Listing.objects.get(id=listing_id, boost_tx_ref=tx_ref)

            # Fallback: if webhook was slow, boost it here
            if not listing.is_boosted:
                listing.is_boosted = True
                listing.boost_expiry = timezone.now() + timedelta(days=7)
                listing.save(update_fields=['is_boosted', 'boost_expiry'])

            return render(request, 'payments/success.html', {
                'message': f'Payment successful! {listing.product} boosted for 7 days.',
                'listing': listing
            })
        except (ValueError, IndexError, Listing.DoesNotExist):
            pass

    return render(request, 'payments/failed.html', {
        'tx_ref': tx_ref,
        'status': status
    })


@csrf_exempt
def payment_callback(request):
    """
    PayChangu hits this webhook when payment completes
    This is what actually sets is_boosted=True - source of truth
    """
    if request.method!= 'POST':
        return HttpResponse(status=405)
    
    try:
        data = json.loads(request.body)

        if data.get('status') == 'success':
            tx_ref = data.get('tx_ref', '')

            if tx_ref.startswith('boost_'):
                try:
                    listing_id = int(tx_ref.split('_')[1])
                    listing = Listing.objects.get(id=listing_id, boost_tx_ref=tx_ref)

                    listing.is_boosted = True
                    listing.boost_expiry = timezone.now() + timedelta(days=7)
                    listing.save(update_fields=['is_boosted', 'boost_expiry'])

                    print(f">>> Boosted listing {listing_id} via webhook")
                except (ValueError, IndexError, Listing.DoesNotExist):
                    print(f">>> Webhook: Listing not found for {tx_ref}")

        return HttpResponse(status=200)
    except Exception as e:
        print(f">>> Webhook error: {e}")
        return HttpResponse(status=400)