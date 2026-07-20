from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from.models import Listing, ListingImage, Conversation, Message

User = get_user_model()

class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 1
    max_num = 10
    fields = ['image']

@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ['product', 'price', 'phone', 'location', 'is_sold', 'created_at']
    list_filter = ['is_sold', 'location']
    search_fields = ['product', 'location']
    inlines = [ListingImageInline]

@admin.register(ListingImage)
class ListingImageAdmin(admin.ModelAdmin):
    list_display = ['listing', 'image']

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # list_display: BaseUserAdmin already has 'email'. Only add phone_number
    list_display = BaseUserAdmin.list_display + ('phone_number',)

    # fieldsets: BaseUserAdmin already has 'email' in 'Personal info'. Only add phone_number
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Lendogo Info', {'fields': ('phone_number',)}),
    )

    # add_fieldsets: Default only has username/passwords. Add email + phone_number here
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'phone_number', 'email'),
        }),
    )

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'listing', 'buyer', 'seller', 'updated_at')
    search_fields = ('buyer__username', 'seller__username', 'listing__product')

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'sender', 'content', 'created_at', 'is_read')
    list_filter = ('is_read', 'created_at')