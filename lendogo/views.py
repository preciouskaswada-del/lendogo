import os
from dotenv import load_dotenv

from django.forms import inlineformset_factory
from.forms import ListingForm, ListingImageForm, SignUpForm
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, get_user_model
from django.contrib.auth.decorators import login_required
from.models import Listing, ListingImage, RentalListing, ListingView, WhatsAppClick, UserProfile, Category
from django.db.models import Q, Count, Sum, F
from urllib.parse import urlencode
from django.contrib import messages
from django.core.mail import send_mail
import random
from django.conf import settings
import secrets
from datetime import date, datetime, timedelta
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from lendogo.chat.models import Conversation, Message
from django.utils import timezone
import json
from django.views.decorators.http import require_POST, require_GET
from django.core.files.storage import default_storage
from decimal import Decimal, InvalidOperation
from django.db import transaction
from payments.airtel import initiate_airtel_payment
import uuid
import re
import requests
import urllib3
import time

load_dotenv()

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

User = get_user_model()

ImageFormSet = inlineformset_factory(
    Listing,
    ListingImage,
    form=ListingImageForm,
    extra=10,
    max_num=10,
    can_delete=True,
    can_delete_extra=False,
)

def home(request):
    query = request.GET.get('q', '').strip()
    location = request.GET.get('location', '').strip()
    sort = request.GET.get('sort', '').strip()
    category_slug = request.GET.get('category', '').strip()

    all_listings = Listing.objects.select_related('seller', 'seller__userprofile', 'category').filter(
        status='ACTIVE'
    )

    if query:
        all_listings = all_listings.filter(
            Q(product__icontains=query) |
            Q(location__icontains=query) |
            Q(description__icontains=query)
        )

    if location:
        all_listings = all_listings.filter(location__iexact=location)

    if category_slug:
        all_listings = all_listings.filter(category__slug=category_slug)

    if sort == 'price_asc':
        all_listings = all_listings.order_by('price')
    elif sort == 'price_desc':
        all_listings = all_listings.order_by('-price')
    elif sort == 'newest':
        all_listings = all_listings.order_by('-is_boosted', '-id')
    elif sort == 'bikes':
        all_listings = all_listings.filter(product__icontains='bike')
    elif sort == 'cars':
        all_listings = all_listings.filter(product__icontains='car')
    elif sort == 'pc':
        all_listings = all_listings.filter(Q(product__icontains='pc') | Q(product__icontains='laptop'))
    elif sort == 'business':
        business_keywords = [
            'shop', 'business', 'salon', 'restaurant', 'store', 'bar', 'hotel', 'lodge',
            'boutique', 'pharmacy', 'clinic', 'garage', 'grocery', 'supermarket',
            'hardware', 'barbershop', 'beauty', 'gym', 'internet', 'catering', 'construction', 'transport'
        ]
        business_q = Q()
        for keyword in business_keywords:
            business_q |= Q(product__icontains=keyword) | Q(location__icontains=keyword)
        all_listings = all_listings.filter(business_q)
    elif sort == 'near_me':
        if request.user.is_authenticated and hasattr(request.user, 'userprofile') and request.user.userprofile.location:
            all_listings = all_listings.filter(location=request.user.userprofile.location)
    else:
        all_listings = all_listings.order_by('-is_boosted', '-bumped_at', '-id')

    locations = Listing.objects.filter(status='ACTIVE').values_list('location', flat=True).distinct().exclude(location__isnull=True).exclude(location='')
    categories = Category.objects.all()

    get_params = request.GET.copy()

    return render(request, 'home.html', {
        'all_listings': all_listings,
        'locations': locations,
        'categories': categories,
        'active_location': location,
        'active_sort': sort,
        'active_category': category_slug,
        'get_params': get_params
    })

def listing_detail(request, pk):
    listing = get_object_or_404(
        Listing.objects.select_related('seller', 'seller__userprofile', 'category').prefetch_related('images'),
        pk=pk,
        status='ACTIVE'
    )

    if request.user!= listing.seller:
        ip = request.META.get('REMOTE_ADDR')
        if ip:
            yesterday = timezone.now() - timedelta(days=1)
            view_exists = ListingView.objects.filter(
                listing=listing,
                ip_address=ip,
                viewed_at__gte=yesterday
            ).exists()

            if not view_exists:
                ListingView.objects.create(listing=listing, ip_address=ip)
                Listing.objects.filter(pk=pk).update(view_count=F('view_count') + 1)

    listing.refresh_from_db(fields=['view_count'])

    show_warning = (
        listing.suspicion_level >= 2 and
        request.user.is_authenticated and
        request.user!= listing.seller
    )

    context = {
        'listing': listing,
        'suspicion_level': listing.suspicion_level,
        'market_avg': listing.market_avg_price,
        'has_market_data': listing.market_avg_price is not None,
        'scam_warning': listing.scam_warning,
        'show_warning': show_warning,
    }
    return render(request, 'detail.html', context)

@login_required(login_url='login')
def create_listing(request):
    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES)
        formset = ImageFormSet(request.POST, request.FILES)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                listing = form.save(commit=False)
                listing.seller = request.user
                listing.status = 'ACTIVE'
                listing.save()
                form.save_m2m()

                formset.instance = listing
                formset.save()

            messages.success(request, 'Listing created successfully!')
            return redirect('listing_detail', pk=listing.pk)
        else:
            messages.error(request, 'Please fix the errors below')
    else:
        form = ListingForm()
        formset = ImageFormSet()

    categories = Category.objects.all()
    return render(request, 'create.html', {'form': form, 'formset': formset, 'categories': categories})

@login_required
def delete_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, seller=request.user)
    listing.delete()
    messages.success(request, 'Listing deleted')
    return redirect('dashboard')

@login_required
def mark_as_sold(request, pk):
    listing = get_object_or_404(Listing, pk=pk, seller=request.user)
    if listing.status!= 'SOLD':
        listing.status = 'SOLD'
        listing.is_sold = True
        listing.save(update_fields=['status', 'is_sold'])

        profile = request.user.userprofile
        profile.total_sales = F('total_sales') + 1
        profile.save(update_fields=['total_sales'])

    messages.success(request, f'{listing.product} marked as sold! This helps improve market prices for everyone.')
    return redirect('dashboard')

@login_required
def edit_listing(request, pk):
    listing = get_object_or_404(Listing, pk=pk, seller=request.user)
    if request.method == 'POST':
        form = ListingForm(request.POST, request.FILES, instance=listing)
        formset = ImageFormSet(request.POST, request.FILES, instance=listing)

        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                listing = form.save(commit=False)
                listing.save()
                form.save_m2m()

                formset.save()

            messages.success(request, 'Listing updated')
            return redirect('dashboard')
    else:
        form = ListingForm(instance=listing)
        formset = ImageFormSet(instance=listing)

    categories = Category.objects.all()
    return render(request, 'edit.html', {
        'form': form,
        'formset': formset,
        'listing': listing,
        'categories': categories
    })

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            if hasattr(user, 'userprofile'):
                user.userprofile.last_seen = timezone.now()
                user.userprofile.save(update_fields=['last_seen'])
            return redirect('/')
    else:
        form = AuthenticationForm()
    return render(request, 'login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('/')

def signup(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.get_or_create(user=user)
            login(request, user)
            return redirect('home')
    else:
        form = SignUpForm()
    return render(request, 'signup.html', {'form': form})

@csrf_exempt
def forgot_password(request):
    if request.method == 'POST':
        identifier = request.POST.get('identifier', '').strip()

        if not identifier:
            return JsonResponse({'status': 'error', 'message': 'Enter your email.'})

        user = None
        masked = None

        if '@' in identifier and '.' in identifier:
            user = User.objects.filter(email__iexact=identifier).first()
            if user:
                masked = user.email[:2] + '****' + user.email[user.email.find('@'):]
        else:
            return JsonResponse({'status': 'error', 'message': 'Please enter your email address.'})

        if not user:
            return JsonResponse({'status': 'error', 'message': 'No account found with that email.'})

        if not user.email:
            return JsonResponse({'status': 'error', 'message': 'This account has no email. Contact support to reset.'})

        code = str(secrets.randbelow(900000) + 100000)
        request.session['reset_code'] = code
        request.session['reset_username'] = user.username
        request.session['masked_contact'] = masked
        request.session.set_expiry(600)

        try:
            send_mail(
                'Lendogo Password Reset',
                f'Your reset code is: {code}\nValid for 10 minutes.\n\nIf you did not request this, ignore this email.',
                settings.DEFAULT_FROM_EMAIL,
                [user.email],
                fail_silently=False,
            )
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': f'Failed to send email: {str(e)}'})

        return JsonResponse({'status': 'success', 'message': f'Code sent to {masked}', 'redirect': '/verify-code/'})

    return render(request, 'forgot.html')

def verify_code(request):
    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        stored_code = request.session.get('reset_code')

        if not stored_code:
            return JsonResponse({'status': 'error', 'message': 'Code expired. Request a new one.'})

        if code == stored_code:
            request.session['code_verified'] = True
            return JsonResponse({'status': 'success', 'message': 'Code verified', 'redirect': '/set-new-password/'})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid code'})

    if 'reset_username' not in request.session:
        return redirect('forgot_password')

    masked = request.session.get('masked_contact', 'your email')
    return render(request, 'verify_code.html', {'masked_contact': masked})

def set_new_password(request):
    if request.method == 'POST':
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        if 'reset_username' not in request.session or not request.session.get('code_verified'):
            messages.error(request, 'Session expired. Start over.')
            return redirect('forgot_password')

        if password1!= password2:
            messages.error(request, 'Passwords do not match')
            return render(request, 'set_new_password.html')

        if len(password1) < 8:
            messages.error(request, 'Password must be at least 8 characters')
            return render(request, 'set_new_password.html')

        try:
            user = User.objects.get(username=request.session['reset_username'])
            user.set_password(password1)
            user.save()
            request.session.flush()
            return redirect('password_reset_done')
        except User.DoesNotExist:
            messages.error(request, 'User not found')
            return render(request, 'set_new_password.html')

    if 'reset_username' not in request.session or not request.session.get('code_verified'):
        return redirect('forgot_password')

    return render(request, 'set_new_password.html')

def password_reset_done(request):
    return render(request, 'password_reset_done.html')

@login_required
def dashboard(request):
    user_listings = Listing.objects.filter(seller=request.user).select_related('seller__userprofile')

    active_listings = user_listings.filter(status='ACTIVE')
    sold_listings = user_listings.filter(status='SOLD')

    now = timezone.now()
    today = now.date()
    yesterday = today - timedelta(days=1)
    week_ago = now - timedelta(days=7)

    views_today = ListingView.objects.filter(
        listing__seller=request.user,
        viewed_at__date=today
    ).count()

    views_yesterday = ListingView.objects.filter(
        listing__seller=request.user,
        viewed_at__date=yesterday
    ).count()

    views_this_week = ListingView.objects.filter(
        listing__seller=request.user,
        viewed_at__gte=week_ago
    ).count()

    whatsapp_clicks_today = WhatsAppClick.objects.filter(
        listing__seller=request.user,
        clicked_at__date=today
    ).count()

    whatsapp_clicks_yesterday = WhatsAppClick.objects.filter(
        listing__seller=request.user,
        clicked_at__date=yesterday
    ).count()

    whatsapp_clicks_week = WhatsAppClick.objects.filter(
        listing__seller=request.user,
        clicked_at__gte=week_ago
    ).count()

    posted_today = user_listings.filter(created_at__date=today).count()
    posted_yesterday = user_listings.filter(created_at__date=yesterday).count()

    sold_today = sold_listings.filter(updated_at__date=today).count()
    sold_yesterday = sold_listings.filter(updated_at__date=yesterday).count()
    sold_this_week = sold_listings.filter(updated_at__gte=week_ago).count()

    stats = {
        'total_listings': user_listings.count(),
        'active_listings': active_listings.count(),
        'sold_listings': sold_listings.count(),
        'total_views': user_listings.aggregate(total=Sum('view_count'))['total'] or 0,
        'views_this_week': views_this_week,
        'views_today': views_today,
        'views_yesterday': views_yesterday,
        'whatsapp_clicks': user_listings.aggregate(total=Sum('whatsapp_clicks'))['total'] or 0,
        'whatsapp_clicks_week': whatsapp_clicks_week,
        'whatsapp_clicks_today': whatsapp_clicks_today,
        'whatsapp_clicks_yesterday': whatsapp_clicks_yesterday,
        'posted_today': posted_today,
        'posted_yesterday': posted_yesterday,
        'sold_today': sold_today,
        'sold_yesterday': sold_yesterday,
        'sold_this_week': sold_this_week,
        'is_verified': request.user.userprofile.is_verified,
    }

    return render(request, 'dashboard.html', {
        'listings': active_listings[:6],
        'stats': stats,
        'now': now
    })

@csrf_exempt
def paychangu_callback(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        print("PayChangu Webhook:", data)

        status = data.get('status')
        tx_ref = data.get('tx_ref')
        print(f"Payment {tx_ref} status: {status}")

    return HttpResponse("OK", status=200)

@login_required
def boost_callback(request):
    tx_ref = request.GET.get('tx_ref') or request.session.get('boost_tx_ref')
    listing_id = request.session.get('boost_listing_id')

    if not tx_ref or not listing_id:
        messages.error(request, 'Invalid payment session.')
        return redirect('dashboard')

    PAYCHANGU_SECRET = getattr(settings, 'PAYCHANGU_SECRET_KEY', None)

    if not PAYCHANGU_SECRET:
        messages.error(request, 'Payment verification failed.')
        return redirect('dashboard')

    try:
        headers = {'Authorization': f'Bearer {PAYCHANGU_SECRET}'}
        response = requests.get(
            f'https://api.paychangu.com/verify-payment/{tx_ref}',
            headers=headers,
            timeout=10,
            verify=settings.PAYCHANGU_VERIFY_SSL
        )

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success' and data['data']['status'] == 'successful':
                listing = Listing.objects.get(id=listing_id, seller=request.user)
                listing.is_boosted = True
                listing.boost_expiry = timezone.now() + timedelta(days=7)
                listing.save()

                messages.success(request, f'Boost activated! {listing.product} will show first for 7 days.')

                if 'boost_tx_ref' in request.session:
                    del request.session['boost_tx_ref']
                if 'boost_listing_id' in request.session:
                    del request.session['boost_listing_id']
            else:
                messages.error(request, 'Payment not successful.')
        else:
            messages.error(request, 'Could not verify payment.')

    except Exception as e:
        messages.error(request, f'Verification error: {str(e)}')

    return redirect('dashboard')

@require_GET
def track_whatsapp_click(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id, status='ACTIVE')
    ip = request.META.get('REMOTE_ADDR')

    if ip:
        hour_ago = timezone.now() - timedelta(hours=1)
        click_exists = WhatsAppClick.objects.filter(
            listing=listing,
            ip_address=ip,
            clicked_at__gte=hour_ago
        ).exists()

        if not click_exists:
            WhatsAppClick.objects.create(listing=listing, ip_address=ip)
            Listing.objects.filter(pk=listing_id).update(
                whatsapp_clicks=F('whatsapp_clicks') + 1
            )

    whatsapp_number = listing.phone or ''
    whatsapp_number = re.sub(r'[\s\-\(\)]', '', whatsapp_number)
    if whatsapp_number.startswith('0'):
        whatsapp_number = '+265' + whatsapp_number[1:]

    whatsapp_url = f"https://wa.me/{whatsapp_number}?text=Hi, I'm interested in your {listing.product} on Lendogo"
    return redirect(whatsapp_url)

@require_POST
def log_blocked_attempt(request, pk):
    listing = get_object_or_404(Listing, pk=pk)
    Listing.objects.filter(pk=pk).update(whatsapp_clicks=F('whatsapp_clicks') + 1)
    return JsonResponse({'status': 'logged'})

@login_required
@require_POST
def start_conversation(request, listing_id):
    listing = get_object_or_404(Listing, id=listing_id)
    seller = listing.seller

    if request.user == seller:
        return JsonResponse({'error': 'Cannot chat with yourself'}, status=400)

    if listing.suspicion_level >= 2 and not request.POST.get('risk_accepted'):
        return JsonResponse({
            'error': 'suspicious_price',
            'message': 'This price is unusually low. Please confirm you understand the risk.',
            'warning': listing.scam_warning,
            'market_avg': str(listing.market_avg_price) if listing.market_avg_price else None,
        }, status=400)

    convo, created = Conversation.objects.get_or_create(
        listing=listing,
        rental=None,
        buyer=request.user,
        seller=seller
    )
    convo.save()
    return redirect('chat:room', convo_id=convo.id)

@login_required
@require_POST
@csrf_exempt
def send_message(request):
    try:
        data = json.loads(request.body)
        convo = get_object_or_404(Conversation, id=data['convo_id'])

        if request.user not in [convo.buyer, convo.seller]:
            return JsonResponse({'error': 'Not allowed'}, status=403)

        content = data.get('text', '').strip()
        if not content:
            return JsonResponse({'error': 'Message cannot be empty'}, status=400)

        msg = Message.objects.create(
            conversation=convo,
            sender=request.user,
            content=content,
        )

        convo.updated_at = timezone.now()
        convo.save(update_fields=['updated_at'])

        return JsonResponse({
            'status': 'ok',
            'id': msg.id,
            'time': msg.created_at.strftime('%H:%M'),
            'text': msg.content
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@login_required
def get_messages(request, convo_id):
    convo = get_object_or_404(Conversation, id=convo_id)
    if request.user not in [convo.buyer, convo.seller]:
        return JsonResponse({'error': 'Not allowed'}, status=403)

    msgs = convo.messages.select_related('sender').all().order_by('created_at')
    msgs.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    data = [{
        'text': m.content,
        'sender': m.sender.username,
        'is_me': m.sender == request.user,
        'time': m.created_at.strftime('%H:%M')
    } for m in msgs]
    return JsonResponse({'messages': data})

@login_required
def chat_room(request, convo_id):
    convo = get_object_or_404(
        Conversation.objects.select_related('buyer', 'seller', 'listing', 'rental'),
        id=convo_id
    )
    if request.user!= convo.buyer and request.user!= convo.seller:
        return HttpResponseForbidden("Not your chat")

    messages = convo.messages.select_related('sender').all().order_by('created_at')
    other_user = convo.seller if request.user == convo.buyer else convo.buyer

    return render(request, 'chat/room.html', {
        'convo': convo,
        'messages': messages,
        'other_user': other_user
    })

@login_required
def rental_page(request):
    rentals = RentalListing.objects.filter(is_active=True).select_related('seller')

    q = request.GET.get('q', '').strip()
    if q:
        rentals = rentals.filter(
            Q(product__icontains=q) |
            Q(description__icontains=q) |
            Q(location__icontains=q)
        )

    category = request.GET.get('category', '').strip()
    if category and hasattr(RentalListing, 'category'):
        rentals = rentals.filter(category=category)

    rentals = rentals.order_by('-created_at')

    unread_count = 0
    if request.user.is_authenticated:
        try:
            unread_count = Message.objects.filter(
                conversation__buyer=request.user,
                is_read=False
            ).exclude(sender=request.user).count()
        except:
            unread_count = 0

    return render(request, 'hire.html', {
        'rentals': rentals,
        'unread_count': unread_count,
        'MEDIA_URL': settings.MEDIA_URL,
    })

@login_required
def post_rental(request):
    if request.method == 'POST':
        product = request.POST.get('product', '').strip()
        description = request.POST.get('description', '').strip()

        if not product:
            messages.error(request, 'Product name is required')
            return render(request, 'post_rental.html')

        price_str = request.POST.get('price', '0').replace(',', '').strip()
        try:
            price = Decimal(price_str) if price_str else Decimal('0')
            if price < 0:
                price = Decimal('0')
            elif price > Decimal('9999999.99'):
                price = Decimal('9999999999.99')
        except (InvalidOperation, ValueError, TypeError):
            price = Decimal('0')

        rental_type = request.POST.get('rental_type', 'day').strip()
        location = request.POST.get('location', '').strip()
        contact = request.POST.get('contact', '').strip()

        category = request.POST.get('category', 'other').strip()
        valid_categories = ['cars', 'ps_system', 'tents', 'chairs', 'halls', 'garden', 'tools', 'electronics', 'sound', 'other']
        if category not in valid_categories:
            category = 'other'

        deposit_str = request.POST.get('deposit_required', '0').replace(',', '').strip()
        try:
            deposit = Decimal(deposit_str) if deposit_str else Decimal('0')
            if deposit < 0:
                deposit = Decimal('0')
            elif deposit > Decimal('9999999.99'):
                deposit = Decimal('9999999999.99')
        except (InvalidOperation, ValueError, TypeError):
            deposit = Decimal('0')

        available_from_str = request.POST.get('available_from', '').strip()
        available_from = timezone.now().date()
        if available_from_str:
            try:
                parsed_date = datetime.strptime(available_from_str, '%Y-%m-%d').date()
                if date(1900, 1, 1) <= parsed_date <= date(9999, 12, 31):
                    available_from = parsed_date
            except (ValueError, TypeError):
                pass

        images = request.FILES.getlist('images')
        image_paths = []
        for img in images[:10]:
            if img.size > 10 * 1024 * 1024:
                continue
            try:
                path = default_storage.save(f'rental_images/{timezone.now().strftime("%Y%m%d_%H%M%S")}_{img.name}', img)
                image_paths.append(settings.MEDIA_URL + path)
            except:
                continue

        video_file = request.FILES.get('video')
        if video_file and video_file.size > 50 * 1024 * 1024:
            video_file = None

        rental_data = {
            'seller': request.user,
            'product': product,
            'description': description,
            'price': price,
            'rental_type': rental_type,
            'location': location,
            'contact': contact,
            'deposit_required': deposit,
            'available_from': available_from,
            'images': image_paths,
            'image': image_paths[0] if image_paths else None,
            'video': video_file
        }

        if hasattr(RentalListing, 'category'):
            rental_data['category'] = category

        rental = RentalListing.objects.create(**rental_data)

        messages.success(request, 'Rental posted successfully!')
        return redirect('rental_page')

    return render(request, 'post_rental.html')
from django.conf import settings

def rental_detail(request, pk):
    rental = get_object_or_404(RentalListing.objects.select_related('seller'), pk=pk, is_active=True)
    RentalListing.objects.filter(pk=pk).update(views=F('views') + 1)
    rental.refresh_from_db(fields=['views'])

    # Safety: ensure images is always a list
    if not rental.images:
        rental.images = []

    return render(request, 'rental_detail.html', {
        'rental': rental,
        'MEDIA_URL': settings.MEDIA_URL,
    })
@login_required
@require_POST
def start_rental_conversation(request, rental_id):
    rental = get_object_or_404(RentalListing, id=rental_id, is_active=True)
    seller = rental.seller

    if request.user == seller:
        messages.error(request, "You can't message yourself.")
        return redirect('rental_detail', pk=rental_id)

    convo, created = Conversation.objects.get_or_create(
        rental=rental,
        listing=None,
        buyer=request.user,
        seller=seller
    )

    convo.save()
    return redirect('chat:room', convo_id=convo.id)

def airtel_checkout(request):
    if request.method == 'POST':
        phone = request.POST.get('phone')
        amount = request.POST.get('amount')

        transaction_id = f"ORDER_{uuid.uuid4().hex[:8]}"

        response = initiate_airtel_payment(phone, int(amount), transaction_id)

        if response.get('status') == 'SUCCESS':
            return render(request, 'payment_pending.html', {
                'message': 'Check your phone to approve payment',
                'ref': transaction_id
            })
        else:
            return render(request, 'payment_failed.html', {
                'error': response.get('message', 'Payment failed')
            })

    return render(request, 'checkout.html')

VERIFY_TOKEN = "mabvuto123"

@csrf_exempt
def whatsapp_webhook(request):
    if request.method == 'GET':
        mode = request.GET.get('hub.mode')
        token = request.GET.get('hub.verify_token')
        challenge = request.GET.get('hub.challenge')

        if mode == 'subscribe' and token == VERIFY_TOKEN:
            return HttpResponse(challenge, status=200)
        return HttpResponse('Forbidden', status=403)

    if request.method == 'POST':
        data = json.loads(request.body)
        print("WHATSAPP DATA:", data)
        return HttpResponse('EVENT_RECEIVED', status=200)