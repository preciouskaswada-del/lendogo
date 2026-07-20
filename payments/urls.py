from django.urls import path
from . import views

urlpatterns = [
    path('boost/<int:listing_id>/', views.boost_listing, name='boost_listing'),
    path('verify/', views.verify_payment, name='verify_payment'),
    path('webhook/', views.payment_callback, name='payment_callback'),
]