import requests
import uuid
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

AIRTEL_AUTH_URL = "https://openapiuat.airtel.africa/auth/oauth2/token"
AIRTEL_COLLECT_URL = "https://openapiuat.airtel.africa/merchant/v1/payments/"

def get_airtel_token():
    data = {
        'client_id': settings.AIRTEL_CLIENT_ID,
        'client_secret': settings.AIRTEL_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    }
    headers = {'Content-Type': 'application/json'}
    try:
        r = requests.post(AIRTEL_AUTH_URL, json=data, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()['access_token']
    except Exception as e:
        logger.error(f"Airtel token error: {e}")
        return None

def initiate_airtel_payment(phone, amount, transaction_id):
    token = get_airtel_token()
    if not token:
        return {'status': 'FAILED', 'message': 'Could not get auth token'}
    
    headers = {
        'Content-Type': 'application/json',
        'X-Country': settings.AIRTEL_COUNTRY,
        'X-Currency': settings.AIRTEL_CURRENCY,
        'Authorization': f'Bearer {token}'
    }
    
    payload = {
        "reference": transaction_id,
        "subscriber": {
            "country": settings.AIRTEL_COUNTRY,
            "currency": settings.AIRTEL_CURRENCY,
            "msisdn": phone
        },
        "transaction": {
            "amount": amount,
            "country": settings.AIRTEL_COUNTRY,
            "currency": settings.AIRTEL_CURRENCY,
            "id": str(uuid.uuid4())
        }
    }
    
    try:
        r = requests.post(AIRTEL_COLLECT_URL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Airtel payment error: {e}")
        return {'status': 'FAILED', 'message': str(e)}