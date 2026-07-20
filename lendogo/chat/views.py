from django.shortcuts import get_object_or_404, render, redirect
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.conf import settings
from django.db.models import Q
from django.core.files.storage import default_storage
from django.contrib.contenttypes.models import ContentType
import os

from lendogo.chat.models import Conversation, Message, HiddenMessage
from lendogo.models import Listing, RentalListing, User
from services.models import Worker

def is_participant(user, conversation):
    """Check if user is buyer or seller. Handles null seller for workers."""
    if user.id == conversation.buyer_id:
        return True
    if conversation.seller_id and user.id == conversation.seller_id:
        return True
    return False

def get_other_party(conversation, user):
    """Returns the other User in convo, or None for workers."""
    if user.id == conversation.buyer_id:
        return conversation.seller # None for workers
    return conversation.buyer

@login_required
def start_conversation_with_listing(request, listing_id):
    try:
        listing = get_object_or_404(Listing, id=listing_id)
        buyer = request.user
        seller = listing.seller

        if buyer.id == seller.id:
            return JsonResponse({'success': False, 'error': 'Cannot message yourself'}, status=400)

        content_type = ContentType.objects.get_for_model(Listing)
        conversation, created = Conversation.objects.get_or_create(
            content_type=content_type,
            object_id=listing.id,
            buyer=buyer,
            seller=seller
        )
        return redirect('chat:chat_room', convo_id=conversation.id)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def start_conversation_with_rental(request, rental_id):
    try:
        rental = get_object_or_404(RentalListing, id=rental_id)
        buyer = request.user
        seller = rental.seller

        if buyer.id == seller.id:
            return JsonResponse({'success': False, 'error': 'Cannot message yourself'}, status=400)

        content_type = ContentType.objects.get_for_model(RentalListing)
        conversation, created = Conversation.objects.get_or_create(
            content_type=content_type,
            object_id=rental.id,
            buyer=buyer,
            seller=seller
        )
        return redirect('chat:chat_room', convo_id=conversation.id)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def start_conversation_with_worker(request, worker_id):
    try:
        worker = get_object_or_404(Worker, id=worker_id, is_active=True, is_verified=True)
        buyer = request.user

        # Workers don't have User accounts, so seller=None
        content_type = ContentType.objects.get_for_model(Worker)
        conversation, created = Conversation.objects.get_or_create(
            content_type=content_type,
            object_id=worker.id,
            buyer=buyer,
            seller=None
        )
        return redirect('chat:chat_room', convo_id=conversation.id)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
def chat_room(request, convo_id):
    try:
        conversation = get_object_or_404(Conversation, id=convo_id)

        if not is_participant(request.user, conversation):
            return JsonResponse({'error': 'Not allowed'}, status=403)

        # Get the actual object: Listing, RentalListing, or Worker
        content_obj = conversation.content_object

        context = {
            'convo': conversation,
            'content_object': content_obj,
        }

        if isinstance(content_obj, Worker):
            context['worker'] = content_obj
            context['chat_type'] = 'worker'
            context['chat_title'] = content_obj.name
            context['chat_photo'] = content_obj.photo.url if content_obj.photo else None
        elif isinstance(content_obj, Listing):
            context['listing'] = content_obj
            context['chat_type'] = 'listing'
            context['other_user'] = get_other_party(conversation, request.user)
            context['chat_title'] = content_obj.product
            context['chat_photo'] = content_obj.image.url if content_obj.image else None
        elif isinstance(content_obj, RentalListing):
            context['rental'] = content_obj
            context['chat_type'] = 'rental'
            context['other_user'] = get_other_party(conversation, request.user)
            context['chat_title'] = content_obj.product
            context['chat_photo'] = content_obj.image.url if content_obj.image else None

        Message.objects.filter(
            conversation=conversation,
            receiver=request.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())

        if conversation.typing_user_id == request.user.id:
            conversation.typing_user_id = None
            conversation.typing_timestamp = None
            conversation.save(update_fields=['typing_user_id', 'typing_timestamp'])

        return render(request, 'chat.html', context)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def serialize_msg(msg, user):
    reply_data = None
    if msg.reply_to:
        sender_name = msg.reply_to.sender.username if msg.reply_to.sender else 'System'
        reply_data = {
            'sender': sender_name,
            'content': msg.reply_to.content[:50] if msg.reply_to.content else '[Image]'
        }

    images_list = msg.images if msg.images else ([msg.image.url] if msg.image else [])

    return {
        'id': int(msg.id),
        'content': msg.content or '',
        'images': images_list,
        'image_url': msg.image.url if msg.image else None,
        'is_image': bool(msg.is_image),
        'created_at': msg.timestamp.isoformat() if msg.timestamp else timezone.now().isoformat(),
        'sender_id': int(msg.sender_id) if msg.sender_id else 0,
        'receiver_id': int(msg.receiver_id) if msg.receiver_id else None,
        'is_me': msg.sender_id == user.id,
        'is_read': bool(msg.is_read),
        'is_edited': bool(msg.is_edited),
        'is_system': bool(msg.is_system),
        'reply_to': reply_data,
        'reply_to_sender': reply_data['sender'] if reply_data else None,
        'reply_to_content': reply_data['content'] if reply_data else None
    }

@require_http_methods(["GET"])
@login_required
def get_messages(request, convo_id):
    try:
        convo = get_object_or_404(Conversation, id=convo_id)
        if not is_participant(request.user, convo):
            return JsonResponse({'error': 'Not participant'}, status=403)

        after_id = int(request.GET.get('after', 0)) if request.GET.get('after') else 0

        Message.objects.filter(
            conversation=convo,
            receiver=request.user,
            is_read=False
        ).update(is_read=True, read_at=timezone.now())

        hidden_ids = HiddenMessage.objects.filter(user=request.user).values_list('message_id', flat=True)

        messages = Message.objects.filter(
            conversation=convo,
            id__gt=after_id
        ).exclude(id__in=hidden_ids).select_related('sender', 'receiver', 'reply_to__sender').order_by('id')[:100]

        data = [serialize_msg(m, request.user) for m in messages]
        return JsonResponse({'messages': data})
    except Exception as e:
        return JsonResponse({'messages': [], 'error': str(e)}, status=500)

@csrf_exempt
@login_required
def send_message(request):
    if request.method!= 'POST':
        return JsonResponse({'status': 'error', 'msg': 'POST required'}, status=405)

    try:
        convo_id = request.POST.get('convo_id')
        content = request.POST.get('content', '').strip()
        reply_to_id = request.POST.get('reply_to_id')
        images = request.FILES.getlist('images')

        if not convo_id:
            return JsonResponse({'status': 'error', 'msg': 'Missing convo_id'})

        conversation = get_object_or_404(Conversation, id=convo_id)

        if not is_participant(request.user, conversation):
            return JsonResponse({'status': 'error', 'msg': 'Not participant'}, status=403)

        if not content and len(images) == 0:
            return JsonResponse({'status': 'error', 'msg': 'Empty message'})

        # For worker chats, receiver is None
        receiver = get_other_party(conversation, request.user)

        reply_to = None
        if reply_to_id:
            reply_to = Message.objects.filter(id=reply_to_id, conversation=conversation).first()

        image_paths = []
        for img in images:
            if img.size > 10 * 1024: # 10MB cap
                continue
            file_path = default_storage.save(f'chat_images/{timezone.now().strftime("%Y%m%d_%H%M%S")}_{img.name}', img)
            image_paths.append(settings.MEDIA_URL + file_path)

        msg = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            receiver=receiver,
            content=content[:5000],
            reply_to=reply_to,
            images=image_paths,
            image=image_paths[0] if len(image_paths) == 1 else None,
            is_image=len(image_paths) > 0
        )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        return JsonResponse({
            'status': 'ok',
            'message': serialize_msg(msg, request.user)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)

@csrf_exempt
@login_required
def edit_message(request):
    if request.method!= 'POST':
        return JsonResponse({'status': 'error', 'msg': 'POST required'}, status=405)

    try:
        msg_id = request.POST.get('edit_id')
        content = request.POST.get('content', '').strip()

        if not msg_id or not content:
            return JsonResponse({'status': 'error', 'msg': 'Missing data'})

        msg = get_object_or_404(Message, id=msg_id, sender=request.user)

        msg.content = content[:5000]
        msg.is_edited = True
        msg.save()

        return JsonResponse({
            'status': 'ok',
            'message': serialize_msg(msg, request.user)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)

@csrf_exempt
@login_required
def bump_conversation(request, convo_id):
    if request.method!= 'POST':
        return JsonResponse({'status': 'error', 'msg': 'POST required'}, status=405)

    try:
        conversation = get_object_or_404(Conversation, id=convo_id)

        if not is_participant(request.user, conversation):
            return JsonResponse({'status': 'error', 'msg': 'Not participant'}, status=403)

        receiver = get_other_party(conversation, request.user)

        msg = Message.objects.create(
            conversation=conversation,
            sender=request.user,
            receiver=receiver,
            content=f"👋 {request.user.username} bumped you!",
            is_system=True
        )

        conversation.updated_at = timezone.now()
        conversation.save(update_fields=['updated_at'])

        return JsonResponse({
            'status': 'ok',
            'message': serialize_msg(msg, request.user)
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'msg': str(e)}, status=500)

@csrf_exempt
@login_required
def delete_message(request, msg_id):
    if request.method!= 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        msg = get_object_or_404(Message, id=msg_id)
        user = request.user
        delete_type = request.POST.get('type')

        if msg.sender_id!= user.id:
            return JsonResponse({'error': 'Not allowed'}, status=403)

        if delete_type == 'me':
            HiddenMessage.objects.get_or_create(user=user, message=msg)
            return JsonResponse({'status': 'hidden'})

        elif delete_type == 'everyone':
            if msg.images:
                for img_url in msg.images:
                    try:
                        img_path = os.path.join(settings.MEDIA_ROOT, img_url.replace(settings.MEDIA_URL, ''))
                        if os.path.exists(img_path):
                            os.remove(img_path)
                    except Exception:
                        pass

            if msg.image:
                try:
                    image_path = os.path.join(settings.MEDIA_ROOT, str(msg.image))
                    if os.path.exists(image_path):
                        os.remove(image_path)
                except Exception:
                    pass

            msg.delete()
            return JsonResponse({'status': 'deleted'})

        return JsonResponse({'error': 'Invalid type'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@login_required
def clear_chat(request, convo_id):
    if request.method!= 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        conversation = get_object_or_404(Conversation, id=convo_id)
        user = request.user
        if not is_participant(user, conversation):
            return JsonResponse({'success': False})

        clear_type = request.POST.get('type')
        messages = Message.objects.filter(conversation=conversation)

        if clear_type == 'me':
            for msg in messages:
                HiddenMessage.objects.get_or_create(user=user, message=msg)
            return JsonResponse({'success': True, 'type': 'me'})

        elif clear_type == 'everyone':
            for msg in messages:
                if msg.images:
                    for img_url in msg.images:
                        try:
                            img_path = os.path.join(settings.MEDIA_ROOT, img_url.replace(settings.MEDIA_URL, ''))
                            if os.path.exists(img_path):
                                os.remove(img_path)
                        except Exception:
                            pass
                if msg.image:
                    try:
                        image_path = os.path.join(settings.MEDIA_ROOT, str(msg.image))
                        if os.path.exists(image_path):
                            os.remove(image_path)
                    except Exception:
                        pass
            messages.delete()
            return JsonResponse({'success': True, 'type': 'everyone'})

        return JsonResponse({'success': False})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@csrf_exempt
@login_required
def delete_conversation(request, convo_id):
    if request.method!= 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        conversation = get_object_or_404(Conversation, id=convo_id)
        user = request.user
        if is_participant(user, conversation):
            for msg in Message.objects.filter(conversation=conversation):
                if msg.images:
                    for img_url in msg.images:
                        try:
                            img_path = os.path.join(settings.MEDIA_ROOT, img_url.replace(settings.MEDIA_URL, ''))
                            if os.path.exists(img_path):
                                os.remove(img_path)
                        except Exception:
                            pass
                if msg.image:
                    try:
                        image_path = os.path.join(settings.MEDIA_ROOT, str(msg.image))
                        if os.path.exists(image_path):
                            os.remove(image_path)
                    except Exception:
                        pass
            Message.objects.filter(conversation=conversation).delete()
            conversation.delete()
            return JsonResponse({'success': True})
        return JsonResponse({'success': False})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@login_required
@require_http_methods(["POST"])
def set_typing(request, convo_id):
    try:
        convo = get_object_or_404(Conversation, id=convo_id)
        if not is_participant(request.user, convo):
            return JsonResponse({'error': 'Not participant'}, status=403)

        convo.typing_user_id = request.user.id
        convo.typing_timestamp = timezone.now()
        convo.save(update_fields=['typing_user_id', 'typing_timestamp'])
        return JsonResponse({'status': 'ok'})
    except Exception:
        return JsonResponse({'status': 'error'}, status=500)

@login_required
@require_http_methods(["GET"])
def get_typing(request, convo_id):
    try:
        convo = get_object_or_404(Conversation, id=convo_id)
        if not is_participant(request.user, convo):
            return JsonResponse({'error': 'Not participant'}, status=403)

        typing_name = None
        if convo.typing_user_id and convo.typing_user_id!= request.user.id:
            if convo.typing_timestamp:
                time_diff = timezone.now() - convo.typing_timestamp
                if time_diff.total_seconds() < 3:
                    typing_user = User.objects.filter(id=convo.typing_user_id).first()
                    if typing_user:
                        typing_name = typing_user.get_full_name() or typing_user.username
                else:
                    convo.typing_user_id = None
                    convo.typing_timestamp = None
                    convo.save(update_fields=['typing_user_id', 'typing_timestamp'])

        return JsonResponse({'typing_name': typing_name})
    except Exception:
        return JsonResponse({'typing_name': None})

@login_required
def inbox(request):
    user = request.user
    conversations = Conversation.objects.filter(
        Q(buyer=user) | Q(seller=user)
    ).select_related('buyer', 'seller', 'content_type').order_by('-updated_at')

    convo_data = []
    for convo in conversations:
        other_user = get_other_party(convo, user)
        last_msg = Message.objects.filter(conversation=convo).order_by('-id').first()
        unread_count = Message.objects.filter(
            conversation=convo,
            receiver=user,
            is_read=False
        ).count()

        # Get display name + photo from content_object
        content_obj = convo.content_object
        if isinstance(content_obj, Worker):
            display_name = content_obj.name
            display_photo = content_obj.photo.url if content_obj.photo else None
        elif hasattr(content_obj, 'product'):
            display_name = content_obj.product
            display_photo = content_obj.image.url if hasattr(content_obj, 'image') and content_obj.image else None
        else:
            display_name = str(content_obj)
            display_photo = None

        convo_data.append({
            'convo': convo,
            'other_user': other_user,
            'display_name': display_name,
            'display_photo': display_photo,
            'last_msg': last_msg,
            'unread_count': unread_count,
        })

    return render(request, 'inbox.html', {'conversations': convo_data})

@login_required
def unread_count(request):
    count = Message.objects.filter(receiver=request.user, is_read=False).count()
    return JsonResponse({'count': count})