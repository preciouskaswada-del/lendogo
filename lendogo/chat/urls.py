from django.urls import path
from lendogo.chat import views

app_name = 'chat'

urlpatterns = [
    path('', views.inbox, name='chat_inbox'),
    path('unread_count/', views.unread_count, name='unread_count'),
    
    # 1. Conversation management - 3 types now
    path('start/listing/<int:listing_id>/', views.start_conversation_with_listing, name='start_chat_listing'),
    path('start/rental/<int:rental_id>/', views.start_conversation_with_rental, name='start_chat_rental'),
    path('start/worker/<int:worker_id>/', views.start_conversation_with_worker, name='start_chat_worker'),
    
    path('room/<int:convo_id>/', views.chat_room, name='chat_room'),
    path('delete_conversation/<int:convo_id>/', views.delete_conversation, name='delete_conversation'),
    
    # 2. Messages - multi-image + reply + edit ready
    path('messages/<int:convo_id>/', views.get_messages, name='get_messages'),
    path('send_message/', views.send_message, name='send_message'),
    path('edit_message/', views.edit_message, name='edit_message'), 
    path('delete_message/<int:msg_id>/', views.delete_message, name='delete_message'),
    path('clear_chat/<int:convo_id>/', views.clear_chat, name='clear_chat'),
    
    # 3. Typing indicators
    path('set_typing/<int:convo_id>/', views.set_typing, name='set_typing'),
    path('get_typing/<int:convo_id>/', views.get_typing, name='get_typing'),
    
    path('bump/<int:convo_id>/', views.bump_conversation, name='bump_conversation'),
]