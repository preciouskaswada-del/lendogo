from django.contrib import admin
from .models import Worker, Skill, Conversation, Message

@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'is_active', 'created_at'] # REMOVED slug
    list_editable = ['is_active']
    search_fields = ['name']
    ordering = ['name']
    # REMOVED prepopulated_fields because we don't have slug field


@admin.register(Worker)
class WorkerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'phone', 
        'skill', 
        'location', 
        'is_verified', 
        'is_active', 
        'trust_score',
        'rating',
        'created_at'
    ]
    
    list_filter = [
        'is_verified', 
        'is_active', 
        'skill', 
        'location',
        'created_at'
    ]
    
    search_fields = [
        'name', 
        'phone', 
        'location', 
        'skill__name'
    ]
    
    # You can now tick verify and trust_score from the list
    list_editable = ['is_verified', 'is_active', 'trust_score']
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('name', 'phone', 'location', 'skill')
        }),
        ('Work Details', {
            'fields': ('years_experience', 'bio', 'has_airtel_money', 'rating', 'reviews_count')
        }),
        ('Photos & Verification', {
            'fields': ('photo', 'id_photo', 'work_photo', 'is_verified', 'is_active', 'trust_score')
        }),
        ('Badges', {
            'fields': ('responds_fast',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    readonly_fields = ['created_at', 'updated_at']
    
    ordering = ['-is_verified', '-created_at'] # Verified first
    list_per_page = 50
    actions = ['verify_workers']

    def verify_workers(self, request, queryset):
        queryset.update(is_verified=True, is_active=True)
    verify_workers.short_description = "Verify and Activate Selected Workers"


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ['id', 'participant_1', 'participant_2', 'listing', 'updated_at']
    list_filter = ['updated_at']
    search_fields = ['participant_1__username', 'participant_2__username']


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ['id', 'sender', 'recipient', 'conversation', 'is_read', 'created_at']
    list_filter = ['is_read', 'created_at']
    search_fields = ['body', 'sender__username', 'recipient__username']