from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db.models import Q, F, Avg, Count, Max
from django.db.models.functions import ACos, Cos, Radians, Sin
from django.core.paginator import Paginator
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.http import JsonResponse, HttpResponse
from django.conf import settings
import logging
import uuid
import json
import requests
import hmac
import hashlib
from.models import Worker, Skill, Conversation, Message
from.forms import WorkerSignupForm, WorkerFilterForm

logger = logging.getLogger(__name__)

VERIFICATION_FEE = 2000
USE_PAYCHANGU = False # SET TO TRUE WHEN YOU WANT PAYMENTS BACK

@cache_page(60 * 2)
@require_http_methods(["GET"])
def services_list(request):
    workers = Worker.objects.filter(
        is_active=True,
        is_verified=True
    ).select_related('skill')

    form = WorkerFilterForm(request.GET or None)

    q = request.GET.get('q', '').strip()
    if q:
        workers = workers.filter(
            Q(name__icontains=q) |
            Q(skill__name__icontains=q) |
            Q(location__icontains=q) |
            Q(bio__icontains=q)
        )

    if form.is_valid():
        skill = form.cleaned_data.get('skill')
        location = form.cleaned_data.get('location')

        if skill:
            workers = workers.filter(skill=skill)
        if location:
            workers = workers.filter(location__icontains=location.strip())

    lat = request.GET.get('lat')
    lng = request.GET.get('lng')

    if lat and lng:
        try:
            lat, lng = float(lat), float(lng)
            workers = workers.annotate(
                distance=6371 * ACos(
                    Cos(Radians(lat)) * Cos(Radians(F('latitude'))) *
                    Cos(Radians(F('longitude')) - Radians(lng)) +
                    Sin(Radians(lat)) * Sin(Radians(F('latitude')))
                )
            ).filter(distance__lte=50, latitude__isnull=False)
        except (ValueError, TypeError):
            lat = lng = None

    # SORT LOGIC - NO BOOST
    sort = request.GET.get('sort', 'recommended')
    if sort == 'rating':
        workers = workers.order_by('-rating', '-is_verified', '-created_at')
    elif sort == 'newest':
        workers = workers.order_by('-created_at', '-id')
    elif sort == 'distance' and lat and lng:
        workers = workers.order_by('distance', '-rating')
    else: # recommended
        workers = workers.order_by('-is_verified', '-rating', '-created_at')

    paginator = Paginator(workers, 20)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    unread_messages_count = 0
    if request.user.is_authenticated:
        unread_messages_count = Message.objects.filter(
            recipient=request.user,
            is_read=False
        ).count()

    context = {
        'workers': page_obj,
        'filter_form': form,
        'skills': Skill.objects.filter(is_active=True).order_by('name')[:8],
        'total_workers': paginator.count,
        'unread_messages_count': unread_messages_count,
    }
    return render(request, 'services/list.html', context)

@login_required
@require_http_methods(["GET"])
def inbox(request):
    user = request.user

    conversations_qs = Conversation.objects.filter(
        Q(participant_1=user) | Q(participant_2=user)
    ).annotate(
        last_msg_time=Max('messages__created_at'),
        unread_count=Count(
            'messages',
            filter=Q(messages__recipient=user, messages__is_read=False)
        )
    ).select_related('listing', 'listing__skill', 'participant_1', 'participant_2').order_by('-last_msg_time')

    conversations = []
    for convo in conversations_qs:
        last_msg = convo.messages.order_by('-created_at').first()
        conversations.append({
            'convo': convo,
            'last_msg': last_msg,
            'last_msg_time': convo.last_msg_time,
            'unread_count': convo.unread_count,
            'is_typing': False,
        })

    return render(request, 'inbox.html', {
        'conversations': conversations
    })

@require_http_methods(["GET", "POST"])
def worker_signup(request):
    if request.method == 'POST':
        form = WorkerSignupForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                worker = form.save(commit=False)
                worker.is_active = False
                worker.is_verified = False
                worker.save()

                logger.info(f"New worker signup: {worker.name} - {worker.phone}")

                if USE_PAYCHANGU:
                    messages.success(
                        request,
                        'Account created! Pay MK2000 to verify and go live instantly.'
                    )
                    return redirect('services:worker_verification_pay', pk=worker.pk)
                else:
                    # Manual verification flow
                    return redirect('services:pending_status', pk=worker.pk)

            except Exception as e:
                logger.error(f"Worker signup failed: {e}")
                messages.error(request, 'Something went wrong. Please try again or WhatsApp us.')
        else:
            logger.warning(f"Invalid signup attempt: {form.errors}")
    else:
        form = WorkerSignupForm()

    return render(request, 'services/signup.html', {'form': form})

# NEW: This handles pending -> approved
@require_http_methods(["GET"])
def pending_status(request, pk):
    worker = get_object_or_404(Worker, pk=pk)

    if worker.is_verified:
        return render(request, 'services/approved.html', {'worker': worker})
    else:
        return render(request, 'services/pending.html', {'worker': worker})

@cache_page(60 * 15)
@require_http_methods(["GET"])
def worker_detail(request, pk, slug=None):
    worker = get_object_or_404(
        Worker.objects.select_related('skill'),
        pk=pk,
        is_active=True,
        is_verified=True
    )

    raw_slug = f"{worker.name}-{worker.skill.name}-{worker.location}"
    canonical_slug = slugify(raw_slug)

    if slug!= canonical_slug:
        return redirect(
            'services:worker_detail_slug',
            pk=pk,
            slug=canonical_slug,
            permanent=True
        )

    return render(request, 'services/detail.html', {
        'worker': worker,
        'page_title': f"{worker.name} - {worker.skill.name} in {worker.location}",
        'canonical_url': request.build_absolute_uri(
            reverse('services:worker_detail_slug', args=[pk, canonical_slug])
        )
    })

@require_http_methods(["GET"])
def worker_verification_pay(request, pk):
    worker = get_object_or_404(Worker, pk=pk)

    if worker.is_verified:
        messages.info(request, 'You are already verified!')
        return redirect(worker.get_absolute_url())

    if worker.verification_paid and not worker.is_verified:
        messages.info(request, 'Payment received. Verifying within 5 minutes.')
        return redirect(worker.get_absolute_url())

    context = {
        'worker': worker,
        'amount': VERIFICATION_FEE
    }
    return render(request, 'services/pay_verify.html', context)

@require_http_methods(["POST"])
def initiate_verification_payment(request, pk):
    worker = get_object_or_404(Worker, pk=pk)

    if worker.is_verified:
        return JsonResponse({'error': 'Already verified'}, status=400)

    tx_ref = f"LENDOGO_VRFY_{worker.id}_{uuid.uuid4().hex[:8].upper()}"
    worker.verification_tx_ref = tx_ref
    worker.save(update_fields=['verification_tx_ref'])

    logger.info(f"PayChangu init for worker {worker.id}")

    payload = {
        "amount": VERIFICATION_FEE,
        "currency": "MWK",
        "email": f"{worker.phone.replace('+', '')}@lendogo.mw",
        "first_name": worker.name.split()[0],
        "last_name": worker.name.split()[-1] if len(worker.name.split()) > 1 else "Worker",
        "callback_url": request.build_absolute_uri(reverse('services:verify_payment_callback')),
        "return_url": request.build_absolute_uri(reverse('services:verify_payment_return', args=[worker.pk])),
        "tx_ref": tx_ref,
        "customization": {
            "title": "Lendogo Verification",
            "description": f"Verification fee for {worker.name}"
        },
        "meta": {
            "worker_id": worker.id
        }
    }

    headers = {
        "Authorization": f"Bearer {settings.PAYCHANGU_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        r = requests.post('https://api.paychangu.com/payment', json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        res = r.json()

        if res.get('status') == 'success':
            return redirect(res['data']['checkout_url'])
        else:
            logger.error(f"PayChangu init failed: {res}")
            messages.error(request, 'Payment failed to start. Try again.')
    except requests.RequestException as e:
        logger.error(f"PayChangu request error: {e}")
        messages.error(request, 'Network error. Try again.')

    return redirect('services:worker_verification_pay', pk=pk)

@csrf_exempt
@require_http_methods(["POST"])
def verify_payment_callback(request):
    signature = request.headers.get('x-paychangu-signature')
    if not signature:
        logger.warning("Webhook missing signature")
        return HttpResponse(status=400)

    expected_sig = hmac.new(
        settings.PAYCHANGU_WEBHOOK_SECRET.encode(),
        request.body,
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(signature, expected_sig):
        logger.warning("Webhook signature mismatch - blocked")
        return HttpResponse(status=401)

    try:
        data = json.loads(request.body)
        logger.info(f"PayChangu webhook: {data}")
    except json.JSONDecodeError:
        return HttpResponse(status=400)

    if data.get('status') == 'success' and data.get('data', {}).get('status') == 'success':
        tx_ref = data['data'].get('tx_ref')
        amount = int(float(data['data'].get('amount', 0)))

        if not tx_ref or amount < VERIFICATION_FEE:
            logger.warning(f"Webhook ignored: amount={amount}, tx_ref={tx_ref}")
            return JsonResponse({'status': 'ignored'}, status=200)

        try:
            worker = Worker.objects.get(verification_tx_ref=tx_ref)

            if not worker.verification_paid:
                worker.is_verified = True
                worker.is_active = True
                worker.verification_paid = True
                worker.verification_paid_at = timezone.now()
                worker.save(update_fields=[
                    'is_verified',
                    'is_active',
                    'verification_paid',
                    'verification_paid_at'
                ])
                logger.info(f"Worker {worker.id} {worker.name} AUTO-VERIFIED via {tx_ref}")

            return JsonResponse({'status': 'success'})

        except Worker.DoesNotExist:
            logger.error(f"Webhook: Worker not found for tx_ref {tx_ref}")

    return JsonResponse({'status': 'failed'}, status=400)

def verify_payment_return(request, pk):
    worker = get_object_or_404(Worker, pk=pk)
    messages.success(request, 'Payment received! Your account will be verified in 1 minute if successful.')
    return redirect(worker.get_absolute_url())

@require_http_methods(["GET"])
def chat_view(request, worker_id):
    worker = get_object_or_404(
        Worker.objects.select_related('skill'),
        id=worker_id,
        is_active=True,
        is_verified=True
    )
    return render(request, 'services/chat.html', {
        'worker': worker,
        'page_title': f"Chat with {worker.name} | Lendogo"
    })