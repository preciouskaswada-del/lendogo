from django.db import models
from django.core.validators import RegexValidator, MinValueValidator, MaxValueValidator
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone
from django.conf import settings
from datetime import timedelta
from django.contrib.auth import get_user_model

User = get_user_model()

# Malawi phone validator: +265XXXXXXXXX
MW_PHONE_VALIDATOR = RegexValidator(
    regex=r'^\+265\d{9}$', 
    message='Phone must be in format +265XXXXXXXXX'
)


# 1. DEFINE SKILL FIRST
class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Skill"
        verbose_name_plural = "Skills"

    def __str__(self):
        return self.name


# 2. THEN WORKER
class Worker(models.Model):
    # Core info
    name = models.CharField(max_length=100, db_index=True)
    phone = models.CharField(
        max_length=13, 
        validators=[MW_PHONE_VALIDATOR], 
        unique=True, 
        db_index=True,
        help_text="Format: +265XXXXXXXXX"
    )
    skill = models.ForeignKey(
        Skill, 
        on_delete=models.PROTECT,
        related_name='workers',
        db_index=True
    )
    location = models.CharField(
        max_length=100, 
        db_index=True, 
        help_text="Area 25, Area 18, City Centre"
    )
    
    # Geolocation for "Near Me" search
    latitude = models.FloatField(null=True, blank=True, db_index=True)
    longitude = models.FloatField(null=True, blank=True, db_index=True)
    
    # Business details
    bio = models.TextField(blank=True, help_text="Describe your experience")
    years_experience = models.PositiveIntegerField(default=0)
    
    # Trust & ratings
    rating = models.FloatField(
        default=5.0, 
        validators=[MinValueValidator(1.0), MaxValueValidator(5.0)],
        db_index=True
    )
    reviews_count = models.PositiveIntegerField(default=0, db_index=True)
    
    # MANUAL VERIFICATION
    is_verified = models.BooleanField(
        default=False, 
        db_index=True, 
        help_text="Tick this manually in admin after checking ID"
    )
    
    # NEW: Only for scam modal
    trust_score = models.IntegerField(
        default=50, 
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0-100. Below 30 = show scam warning on profile"
    )
    
    has_airtel_money = models.BooleanField(default=True)
    
    # Media
    photo = models.ImageField(upload_to='workers/photos/%Y/%m/', blank=True, null=True)
    id_photo = models.ImageField(
        upload_to='workers/ids/%Y/%m/', 
        help_text="National ID for verification"
    )
    work_photo = models.ImageField(upload_to='workers/work/%Y/%m/', blank=True, null=True)
    
    # Status
    is_active = models.BooleanField(
        default=False, 
        db_index=True, 
        help_text="Show on public site after you verify"
    )
    responds_fast = models.BooleanField(default=False, help_text="Badge: Responds in 1hr")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_verified', '-rating', 'name'] # Verified first
        verbose_name = "Worker"
        verbose_name_plural = "Workers"
        indexes = [
            models.Index(fields=['is_active', 'is_verified', 'skill']),
            models.Index(fields=['location']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['latitude', 'longitude']),
            models.Index(fields=['trust_score']),
        ]
        constraints = [
            models.CheckConstraint(
                check=models.Q(rating__gte=1.0) & models.Q(rating__lte=5.0),
                name='rating_range_check'
            ),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.skill.name}"
    
    def get_absolute_url(self):
        raw_slug = f"{self.name}-{self.skill.name}-{self.location}"
        slug = slugify(raw_slug)
        return reverse('services:worker_detail_slug', args=[self.pk, slug])
    
    @property
    def whatsapp_link(self):
        if self.phone and self.phone.startswith('+'):
            return f"https://wa.me/{self.phone[1:]}?text=Hi {self.name}, I found you on Lendogo. Are you available for a {self.skill.name} job?"
        return "#"
    
    @property 
    def is_new(self):
        """Badge for workers joined in last 7 days"""
        return self.created_at >= timezone.now() - timedelta(days=7)
    
    def save(self, *args, **kwargs):
        # When you verify manually, also activate
        if self.is_verified and not self.is_active:
            self.is_active = True
        super().save(*args, **kwargs)
        


class Conversation(models.Model):
    participant_1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_conversations_as_p1')
    participant_2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_conversations_as_p2')
    
    # Optional: link to a worker listing
    listing = models.ForeignKey(Worker, on_delete=models.CASCADE, null=True, blank=True, related_name='conversations')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['participant_1', 'participant_2', 'listing']
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.participant_1} <-> {self.participant_2}"


class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_sent_messages')
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='service_received_messages')
    
    body = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"From {self.sender} to {self.recipient}"
