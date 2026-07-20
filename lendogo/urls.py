from django.urls import path, include
from . import views
from django.contrib.auth import views as auth_views  
from django.contrib.auth.views import LogoutView
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from payments import views as payment_views

urlpatterns = [
    path('', views.home, name='home'),
    
    path('chat/', include('lendogo.chat.urls', namespace='chat')),
    path('services/', include('services.urls')), 
    path('payments/', include('payments.urls')), 
    
    path('hire/', views.rental_page, name='rental_page'),
    path('hire/post/', views.post_rental, name='post_rental'),
    path('hire/<int:pk>/', views.rental_detail, name='rental_detail'),
    path('hire/<int:rental_id>/chat/', views.start_rental_conversation, name='start_rental_conversation'),
    
    path('listing/<int:pk>/', views.listing_detail, name='listing_detail'),
    path('listing/<int:pk>/edit/', views.edit_listing, name='edit_listing'),
    path('listing/<int:pk>/delete/', views.delete_listing, name='delete_listing'),
    path('listing/<int:pk>/sold/', views.mark_as_sold, name='mark_as_sold'),
    path('listing/<int:listing_id>/chat/', views.start_conversation, name='start_conversation'),
    
    path('checkout/airtel/', views.airtel_checkout, name='airtel_checkout'),
    
    
    path('whatsapp/<int:listing_id>/', views.track_whatsapp_click, name='track_whatsapp_click'),
    
    # AUTH: MVP - username + email + password only
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', LogoutView.as_view(next_page='home', http_method_names=['get', 'post']), name='logout'),
    path('signup/', views.signup, name='signup'),
    
    # PASSWORD RESET: Email only, 3-step flow
    path('forgot-password/', views.forgot_password, name='forgot_password'),
    path('verify-code/', views.verify_code, name='verify_code'),
    path('set-new-password/', views.set_new_password, name='set_new_password'),
    path('password-reset-success/', views.password_reset_done, name='password_reset_done'),
    
    path('create/', views.create_listing, name='create_listing'),
    
    # Redirect to dashboard so bookmarks don't 404
    path('profile/', RedirectView.as_view(url='/dashboard/', permanent=True)),
    path('dashboard/', views.dashboard, name='dashboard'),
    
    path('api/listing/<int:pk>/blocked-attempt/', views.log_blocked_attempt, name='blocked_attempt'),
    
    path('webhook', views.whatsapp_webhook, name='webhook'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)