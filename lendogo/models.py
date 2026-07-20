from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils import timezone
from django.db.models import JSONField, Avg, Q
from django.core.validators import MinValueValidator
from datetime import timedelta
from decimal import Decimal
from phonenumber_field.modelfields import PhoneNumberField

class User(AbstractUser):
    """
    Custom user for future auth flexibility.
    Phone is REQUIRED for SMS password reset. Email is optional backup.
    """
    email = models.EmailField(blank=True, null=True, db_index=True, help_text="Optional. Used for email password reset if provided")

    phone_number = PhoneNumberField(
        unique=True,
        db_index=True,
        help_text="REQUIRED. E.164 format: +265991234567. Used for SMS reset + WhatsApp + Airtel Money"
    )

    USERNAME_FIELD = 'username'
    REQUIRED_FIELDS = ['phone_number']

    def __str__(self):
        return self.username or str(self.phone_number) or str(self.id)

class UserProfile(models.Model):
    """
    OneToOne for profile data. Keeps User table lean.
    is_verified drives 'Lendogo Verified' badge = trust = higher prices.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='userprofile')
    last_seen = models.DateTimeField(default=timezone.now, db_index=True)
    location = models.CharField(max_length=200, blank=True, default='')
    is_verified = models.BooleanField(default=False, db_index=True)
    total_sales = models.PositiveIntegerField(default=0)

    def is_online(self):
        return timezone.now() - self.last_seen < timedelta(minutes=2)

    def __str__(self):
        return f'{self.user.username} profile'

class Category(models.Model):
    """
    Categories auto-learn market prices from ACTIVE listings.
    """
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=100, unique=True, db_index=True)
    scam_keywords = models.TextField(blank=True, default='')
    min_sample_size = models.PositiveIntegerField(default=2, help_text="Min ACTIVE listings needed before scam detection activates")

    @property
    def market_avg_price(self):
        """AUTO-CALCULATED: Average price from ACTIVE listings in last 90 days"""
        ninety_days_ago = timezone.now() - timedelta(days=90)
        avg = self.listings.filter(
            status='ACTIVE',
            created_at__gte=ninety_days_ago,
            price__gt=0
        ).aggregate(avg_price=Avg('price'))['avg_price']
        return int(avg) if avg else 0

    @property
    def has_enough_data(self):
        ninety_days_ago = timezone.now() - timedelta(days=90)
        count = self.listings.filter(
            status='ACTIVE',
            created_at__gte=ninety_days_ago,
            price__gt=0
        ).count()
        return count >= self.min_sample_size

    def __str__(self):
        avg = self.market_avg_price
        if avg > 0:
            return f"{self.name} - MK {avg:,} avg"
        return f"{self.name} - Learning prices..."

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

class Listing(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('SOLD', 'Sold'),
        ('INACTIVE', 'Inactive'),
        ('EXPIRED', 'Expired'),
    ]

    seller = models.ForeignKey(User, on_delete=models.CASCADE, null=True, related_name='listings')
    product = models.CharField(max_length=200, default='Unnamed Item', db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    phone = models.CharField(max_length=20, blank=True, default='')
    description = models.TextField(blank=True, default='')
    location = models.CharField(max_length=100, blank=True, default='')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='listings')

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE', db_index=True)
    is_sold = models.BooleanField(default=False, db_index=True)

    # BOOST: Manual tick in admin. Auto expires after 7 days
    is_boosted = models.BooleanField(default=False, db_index=True, help_text="Tick to boost for 7 days. Shows at top of home")
    boost_started_at = models.DateTimeField(null=True, blank=True, help_text="Auto set when you tick boost")
    boost_tx_ref = models.CharField(max_length=100, null=True, blank=True, help_text="Keep for paychangu later")

    view_count = models.PositiveIntegerField(default=0)
    whatsapp_clicks = models.PositiveIntegerField(default=0)

    video = models.FileField(upload_to='listing_videos/', null=True, blank=True)

    # AUTO VERIFICATION + SCAM DETECTION
    photo_verified = models.BooleanField(default=False, db_index=True)
    is_lendogo_verified = models.BooleanField(default=False, db_index=True)
    suspicion_level = models.IntegerField(default=0, db_index=True, help_text="0=safe, 1=low, 2=medium, 3=high. Auto")
    scam_warning = models.TextField(blank=True, null=True)
    market_avg_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    last_scanned = models.DateTimeField(null=True, blank=True, db_index=True)
    scam_score = models.IntegerField(default=0, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    bumped_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ['-is_boosted', '-bumped_at', '-created_at']  # Boosted always first
        indexes = [
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['location', 'status']),
            models.Index(fields=['is_boosted', 'status', '-created_at']),
            models.Index(fields=['seller', 'status']),
            models.Index(fields=['whatsapp_clicks']),
            models.Index(fields=['suspicion_level']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['product', 'status', 'suspicion_level']),
            models.Index(fields=['price']),
            models.Index(fields=['last_scanned']),
        ]

    @property
    def display_image(self):
        """Returns first image that actually has a file. Never crashes."""
        if not self.pk:
            return None
        for img in self.images.all().order_by('id'):
            if img.image and img.image.name:
                try:
                    img.image.file
                    return img
                except (ValueError, OSError):
                    continue
        return None

    @property
    def has_valid_images(self):
        return self.display_image is not None

    def run_scam_check(self):
        """AUTO: Compare price to category average. Flag if too low"""
        if not self.category or not self.category.has_enough_data:
            self.suspicion_level = 0
            self.scam_warning = None
            self.market_avg_price = None
            return

        avg_price = self.category.market_avg_price
        self.market_avg_price = avg_price

        if avg_price > 0:
            price_diff_percent = ((avg_price - float(self.price)) / avg_price) * 100
            if price_diff_percent >= 50:
                self.suspicion_level = 3
                self.scam_warning = f"WARNING: Price is {int(price_diff_percent)}% below market average of MK {avg_price:,}. Too good to be true?"
            elif price_diff_percent >= 30:
                self.suspicion_level = 2
                self.scam_warning = f"Caution: Price is {int(price_diff_percent)}% below market average of MK {avg_price:,}"
            elif price_diff_percent >= 15:
                self.suspicion_level = 1
                self.scam_warning = f"Note: Price is {int(price_diff_percent)}% below market average"
            else:
                self.suspicion_level = 0
                self.scam_warning = None
        self.scam_score = self.suspicion_level * 30
        self.last_scanned = timezone.now()

    def save(self, *args, **kwargs):
        self.is_sold = (self.status == 'SOLD')

        # === BOOST LOGIC: 7 DAY AUTO EXPIRE ===
        if self.is_boosted:
            # If just ticked now, set start time
            if not self.boost_started_at:
                self.boost_started_at = timezone.now()
            
            # If 7 days passed, auto unboost
            if self.boost_started_at and timezone.now() > self.boost_started_at + timedelta(days=7):
                self.is_boosted = False
                self.boost_started_at = None
        else:
            # If unticked manually, clear the date
            self.boost_started_at = None

        super().save(*args, **kwargs) # Save first to get PK

        self.run_scam_check()

        # === AUTO VERIFICATION ===
        has_image = self.has_valid_images
        price_ok = self.suspicion_level <= 1
        new_photo_verified = has_image and price_ok

        seller_verified = False
        seller_sales = 0
        if self.seller_id:
            try:
                profile = self.seller.userprofile
                seller_verified = profile.is_verified
                seller_sales = profile.total_sales
            except UserProfile.DoesNotExist:
                pass

        new_lendogo_verified = (seller_verified and self.suspicion_level == 0 and seller_sales >= 1 and has_image)

        if (self.photo_verified != new_photo_verified or self.is_lendogo_verified != new_lendogo_verified):
            self.photo_verified = new_photo_verified
            self.is_lendogo_verified = new_lendogo_verified
            super().save(update_fields=['photo_verified', 'is_lendogo_verified', 'suspicion_level', 'scam_warning', 'market_avg_price', 'last_scanned', 'scam_score', 'is_boosted', 'boost_started_at'])

    def __str__(self):
        return self.product

class ListingView(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='view_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True, db_index=True)
    viewed_at = models.DateTimeField(auto_now_add=True, db_index=True)

class WhatsAppClick(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='whatsapp_logs')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    clicked_at = models.DateTimeField(auto_now_add=True, db_index=True)

class ListingImage(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='listings/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

class ListingVideo(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='videos')
    video = models.FileField(upload_to='listings/videos/', help_text="MP4, max 50MB")
    uploaded_at = models.DateTimeField(auto_now_add=True)

class Conversation(models.Model):
    listing = models.ForeignKey(Listing, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    rental = models.ForeignKey('RentalListing', on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    buyer = models.ForeignKey(User, related_name='buyer_convos', on_delete=models.CASCADE)
    seller = models.ForeignKey(User, related_name='seller_convos', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [['listing', 'buyer', 'seller'], ['rental', 'buyer', 'seller']]
        ordering = ['-updated_at']

class Message(models.Model):
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField(default='')
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

class RentalListing(models.Model):
    RENTAL_TYPE_CHOICES = [('hour', 'Per Hour'),('day', 'Per Day'),('week', 'Per Week'),('month', 'Per Month')]
    CATEGORY_CHOICES = [('cars', 'Cars & Vehicles'),('ps_system', 'PS / Gaming Systems'),('tents', 'Tents'),('chairs', 'Chairs'),('halls', 'Halls for Weddings'),('garden', 'Garden Equipment'),('tools', 'Tools & Equipment'),('electronics', 'Electronics'),('sound', 'Sound Systems'),('other', 'Other')]

    seller = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rental_listings')
    product = models.CharField(max_length=200, default='Unnamed Item')
    description = models.TextField(blank=True, default='')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    rental_type = models.CharField(max_length=10, choices=RENTAL_TYPE_CHOICES, default='day')
    location = models.CharField(max_length=100, blank=True, default='Lilongwe')
    contact = models.CharField(max_length=50, blank=True, default='')
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='other', db_index=True)
    image = models.ImageField(upload_to='rental_images/', blank=True, null=True)
    images = JSONField(default=list, blank=True)
    video = models.FileField(upload_to='rental_videos/', blank=True, null=True)
    deposit_required = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    available_from = models.DateField(default=timezone.now)
    views = models.PositiveIntegerField(default=0, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True, db_index=True)

    def __str__(self):
        return f"{self.product} - {self.get_rental_type_display()} MK{self.price}"

    def get_rental_type_display(self):
        return dict(self.RENTAL_TYPE_CHOICES).get(self.rental_type, 'Per Day')