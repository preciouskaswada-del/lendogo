from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import JSONField
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from lendogo.models import User  # adjust path if needed

class Conversation(models.Model):
    """
    Handles chats for Listing, RentalListing, or Worker.
    Uses GenericForeignKey to support any object type.
    """
    buyer = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='buyer_conversations'
    )
    seller = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='seller_conversations',
        null=True, 
        blank=True  # Null for Workers that don't have User accounts yet
    )
    
    # Generic relation: supports Listing, RentalListing, Worker, etc
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    typing_user_id = models.BigIntegerField(null=True, blank=True)
    typing_timestamp = models.DateTimeField(null=True, blank=True)

    cleared_for_buyer = models.BooleanField(default=False)
    cleared_for_seller = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['buyer', 'seller', 'content_type', 'object_id'],
                name='unique_conversation_per_object'
            ),
        ]
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['buyer', 'seller', 'updated_at']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['typing_user_id', 'typing_timestamp']),
        ]

    def __str__(self):
        obj_name = str(self.content_object) if self.content_object else "Unknown"
        seller_name = self.seller.username if self.seller else "Worker"
        return f"{self.buyer.username} + {seller_name} - {obj_name}"

    def clean(self):
        if self.buyer_id and self.seller_id and self.buyer == self.seller:
            raise ValidationError("Buyer and seller cannot be the same user")
        if self.typing_timestamp:
            min_date = timezone.datetime(1900, 1, 1, tzinfo=timezone.utc)
            max_date = timezone.datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            if not (min_date <= self.typing_timestamp <= max_date):
                raise ValidationError("typing_timestamp out of valid range 1900-9999")

    def save(self, *args, **kwargs):
        self.full_clean(exclude=['updated_at'])
        super().save(*args, **kwargs)


class Message(models.Model):
    conversation = models.ForeignKey(
        Conversation, 
        on_delete=models.CASCADE, 
        related_name='messages'
    )
    sender = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='sent_messages'
    )
    receiver = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='received_messages', 
        null=True, 
        blank=True  # Null for worker chats where receiver isn't a User
    ) 
    
    content = models.TextField(blank=True, max_length=5000)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    
    image = models.ImageField(upload_to='chat_images/', blank=True, null=True)
    images = JSONField(default=list, blank=True)
    is_image = models.BooleanField(default=False)
    
    deleted_for_sender = models.BooleanField(default=False)

    reply_to = models.ForeignKey(
        'self', 
        null=True, 
        blank=True, 
        on_delete=models.SET_NULL, 
        related_name='replies'
    )
    
    is_edited = models.BooleanField(default=False)
    is_system = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']
        indexes = [
            models.Index(fields=['conversation', 'timestamp']),
            models.Index(fields=['receiver', 'is_read']),
            models.Index(fields=['sender', 'timestamp']),
            models.Index(fields=['reply_to']),
        ]

    def __str__(self):
        return f"{self.sender.username}: {self.content[:30] if self.content else '📷 image'}"

    def clean(self):
        if not self.content.strip() and not self.is_image and not self.image and not self.images:
            raise ValidationError("Message must have content or be an image")
        if len(self.content) > 5000:
            raise ValidationError("Message too long. Max 5000 characters.")
        if self.read_at:
            min_date = timezone.datetime(1900, 1, 1, tzinfo=timezone.utc)
            max_date = timezone.datetime(9999, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
            if not (min_date <= self.read_at <= max_date):
                raise ValidationError("read_at out of valid range 1900-9999")
        if self.images:
            if not isinstance(self.images, list):
                raise ValidationError("images must be a list")
            if len(self.images) > 10:
                raise ValidationError("Max 10 images per message")
            for url in self.images:
                if not isinstance(url, str) or len(url) > 2000:
                    raise ValidationError("Each image URL must be a string under 2000 chars")


class HiddenMessage(models.Model):
    user = models.ForeignKey(
        User, 
        on_delete=models.CASCADE, 
        related_name='hidden_messages'
    )
    message = models.ForeignKey(
        Message, 
        on_delete=models.CASCADE, 
        related_name='hidden_by'
    )
    hidden_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'message'], name='unique_hidden_message')
        ]
        indexes = [
            models.Index(fields=['user', 'message']),
            models.Index(fields=['hidden_at']),
        ]
    
    def __str__(self):
        return f"{self.user.username} hid msg {self.message.id}"