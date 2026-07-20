from django.urls import path, re_path
from django.views.generic import TemplateView
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services_list, name='services_list'),
    path('join/', views.worker_signup, name='worker_signup'),
    path('register/', views.worker_signup, name='worker_signup_alias'),

    # === MESSAGES INBOX ===
    path('messages/', views.inbox, name='inbox'),

    # === PAYMENT VERIFICATION FLOW ===
    path('worker/<int:pk>/verify/', views.worker_verification_pay, name='worker_verification_pay'),
    path('worker/<int:pk>/verify/pay/', views.initiate_verification_payment, name='initiate_verification_payment'),
    path('verify/callback/', views.verify_payment_callback, name='verify_payment_callback'),
    path('worker/<int:pk>/verify/return/', views.verify_payment_return, name='verify_payment_return'),

    # Worker detail pages
    path('worker/<int:pk>/', views.worker_detail, name='worker_detail'),
    re_path(
        r'^worker/(?P<pk>\d+)/(?P<slug>[\w-]+)/$',
        views.worker_detail,
        name='worker_detail_slug'
    ),
    path('chat/<int:worker_id>/', views.chat_view, name='chat'),
    path('health/', TemplateView.as_view(template_name='services/health.html'), name='health'),
    path('join/pending/<int:pk>/', views.pending_status, name='pending_status'),
]