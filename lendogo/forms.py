from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import get_user_model
from decimal import Decimal, InvalidOperation
import re
import magic
from.models import Listing, ListingImage, RentalListing

User = get_user_model()

MAX_PRICE = Decimal('999999999.99')
MAX_VIDEO_SIZE = 50 * 1024 * 1024
MAX_IMAGE_SIZE = 10 * 1024 * 1024
ALLOWED_VIDEO_TYPES = {'video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/x-matroska'}
ALLOWED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}
MW_PHONE_REGEX = re.compile(r'^(\+265|0)[89]\d{8}$')
DANGEROUS_CHARS = re.compile(r'[<>"\'%;(){}]')

class ListingForm(forms.ModelForm):
    price = forms.CharField(
        max_length=25,
        widget=forms.NumberInput(attrs={
            'class': 'w-full p-2 border rounded',
            'inputmode': 'numeric',
            'pattern': '[0-9]*'
        })
    )

    class Meta:
        model = Listing
        fields = [
            'product', 'price', 'description', 'phone', 'location',
            'latitude', 'longitude', 'video',
        ]
        widgets = {
            'product': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. Huawei Mate 9',
                'maxlength': '200'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. Battery lidafufuma komaso power button idazukapo',
                'rows': 6,
                'maxlength': '500'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. 0984555865',
                'inputmode': 'tel'
            }),
            'location': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. Area 23, Lilongwe',
                'maxlength': '100'
            }),
            'latitude': forms.HiddenInput(),
            'longitude': forms.HiddenInput(),
            'video': forms.FileInput(attrs={
                'class': 'w-full p-2 border rounded',
                'accept': 'video/mp4,video/quicktime,video/x-msvideo'
            })
        }

    def clean_price(self):
        price_raw = str(self.cleaned_data.get('price', '')).strip()
        if not price_raw:
            raise ValidationError("Price is required")
        price_clean = re.sub(r'[^\d.]', '', price_raw)
        if not price_clean or price_clean == '.':
            raise ValidationError("Enter a valid price, e.g. 300000")
        try:
            price_decimal = Decimal(price_clean)
        except InvalidOperation:
            raise ValidationError("Invalid price format")
        if price_decimal <= 0:
            raise ValidationError("Price must be greater than 0")
        if price_decimal > MAX_PRICE:
            raise ValidationError(f"Price cannot exceed {MAX_PRICE:,.0f} MWK")
        return price_decimal.quantize(Decimal('0.01'))

    def clean_phone(self):
        phone = str(self.cleaned_data.get('phone', '')).strip()
        phone = re.sub(r'[\s\-\(\)]', '', phone)
        if not phone:
            raise ValidationError("Phone/WhatsApp number required")
        if not MW_PHONE_REGEX.match(phone):
            raise ValidationError("Use: +265991234567 or 0991234567 or 0881234567")
        if phone.startswith('0'):
            phone = '+265' + phone[1:]
        return phone

    def clean_product(self):
        product = str(self.cleaned_data.get('product', '')).strip()
        if len(product) < 3:
            raise ValidationError("Product name too short. Min 3 characters.")
        if DANGEROUS_CHARS.search(product):
            raise ValidationError("Product name contains invalid characters: < > \" ' % ;")
        return product

    def clean_description(self):
        desc = str(self.cleaned_data.get('description', '')).strip()
        if len(desc) < 10:
            raise ValidationError("Description too short. Min 10 characters helps buyers.")
        return desc

    def clean_video(self):
        video: UploadedFile = self.cleaned_data.get('video')
        if not video:
            return video
        if video.size > MAX_VIDEO_SIZE:
            raise ValidationError(f"Video is {video.size / 1024 / 1024:.1f}MB. Max: 50MB")
        if video.size < 1024:
            raise ValidationError("Video file appears empty or corrupted")
        try:
            file_head = video.read(2048)
            video.seek(0)
            mime = magic.from_buffer(file_head, mime=True)
            if mime not in ALLOWED_VIDEO_TYPES:
                raise ValidationError("Only MP4, MOV, AVI, MKV allowed")
        except Exception:
            raise ValidationError("Cannot verify video. File may be corrupted.")
        video.name = re.sub(r'[^a-zA-Z0-9._-]', '', video.name)[:100]
        return video

    def clean_latitude(self):
        lat = self.cleaned_data.get('latitude')
        if lat is not None:
            try:
                lat_f = float(lat)
                if not -90 <= lat_f <= 90:
                    raise ValidationError("Invalid latitude")
                return round(lat_f, 6)
            except (ValueError, TypeError):
                raise ValidationError("Invalid latitude")
        return lat

    def clean_longitude(self):
        lng = self.cleaned_data.get('longitude')
        if lng is not None:
            try:
                lng_f = float(lng)
                if not -180 <= lng_f <= 180:
                    raise ValidationError("Invalid longitude")
                return round(lng_f, 6)
            except (ValueError, TypeError):
                raise ValidationError("Invalid longitude")
        return lng

class ListingImageForm(forms.ModelForm):
    class Meta:
        model = ListingImage
        fields = ['image']
        widgets = {
            'image': forms.FileInput(attrs={
                'class': 'img-swap w-full p-2 border rounded',
                'accept': 'image/jpeg,image/png,image/webp'
            })
        }

    def clean_image(self):
        image: UploadedFile = self.cleaned_data.get('image')
        if not image:
            return image
        if image.size > MAX_IMAGE_SIZE:
            raise ValidationError(f"Image is {image.size / 1024 / 1024:.1f}MB. Max: 10MB")
        try:
            file_head = image.read(2048)
            image.seek(0)
            mime = magic.from_buffer(file_head, mime=True)
            if mime not in ALLOWED_IMAGE_TYPES:
                raise ValidationError("Only JPG, PNG, WebP images allowed")
        except Exception:
            raise ValidationError("Cannot verify image. File may be corrupted.")
        image.name = re.sub(r'[^a-zA-Z0-9._-]', '', image.name)[:100]
        return image

class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'w-full p-2 border rounded',
            'placeholder': 'Optional - for password reset'
        }),
        help_text="Optional. Add it to reset password via Gmail."
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'w-full p-2 border rounded',
            'placeholder': 'E.g. james_banda'
        })
        self.fields['username'].help_text = "Pick any name you'll remember"
        self.fields['password1'].widget.attrs.update({'class': 'w-full p-2 border rounded'})
        self.fields['password1'].help_text = "Lembani password yomwe mungakumbukire. Musaiwale."
        self.fields['password2'].widget.attrs.update({'class': 'w-full p-2 border rounded'})
        self.fields['password2'].help_text = "Repeat password"

    def clean_email(self):
        email = self.cleaned_data.get('email', '').strip().lower()
        if email and User.objects.filter(email=email).exists():
            raise ValidationError("Email already registered")
        return email or ''

    def clean_username(self):
        username = self.cleaned_data.get('username', '').strip()
        if DANGEROUS_CHARS.search(username):
            raise ValidationError("Username contains invalid characters: < > \" ' % ;")
        if len(username) < 3:
            raise ValidationError("Username too short. Min 3 characters.")
        return username

class RentalListingForm(forms.ModelForm):
    price = forms.CharField(
        max_length=25,
        widget=forms.NumberInput(attrs={
            'class': 'w-full p-2 border rounded',
            'placeholder': 'e.g. 5,000',
            'inputmode': 'numeric'
        })
    )

    deposit_required = forms.CharField(
        max_length=25,
        required=False,
        widget=forms.NumberInput(attrs={
            'class': 'w-full p-2 border rounded',
            'placeholder': '0 if no deposit needed',
            'inputmode': 'numeric'
        })
    )

    class Meta:
        model = RentalListing
        fields = [
            'product', 'description', 'price', 'rental_type', 'location',
            'contact', 'category', 'image', 'video', 'deposit_required',
            'available_from'
        ]
        widgets = {
            'product': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. Power Drill 500W',
                'maxlength': '200'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'Describe condition, what it includes, rental rules',
                'rows': 5,
                'maxlength': '500'
            }),
            'rental_type': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'location': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': 'e.g. Area 49, Lilongwe',
                'maxlength': '100'
            }),
            'contact': forms.TextInput(attrs={
                'class': 'w-full p-2 border rounded',
                'placeholder': '0984xxxxxx - optional if same as profile',
                'inputmode': 'tel'
            }),
            'category': forms.Select(attrs={'class': 'w-full p-2 border rounded'}),
            'image': forms.FileInput(attrs={
                'class': 'w-full p-2 border rounded',
                'accept': 'image/*'
            }),
            'video': forms.FileInput(attrs={
                'class': 'w-full p-2 border rounded',
                'accept': 'video/*'
            }),
            'available_from': forms.DateInput(attrs={
                'class': 'w-full p-2 border rounded',
                'type': 'date'
            }),
        }

    def clean_price(self):
        return ListingForm.clean_price(self)

    def clean_deposit_required(self):
        deposit_raw = str(self.cleaned_data.get('deposit_required', '0')).strip()
        if not deposit_raw:
            return Decimal('0.00')
        deposit_clean = re.sub(r'[^\d.]', '', deposit_raw)
        try:
            deposit = Decimal(deposit_clean or '0')
            if deposit < 0:
                raise ValidationError("Deposit cannot be negative")
            if deposit > MAX_PRICE:
                raise ValidationError("Deposit too large")
            return deposit.quantize(Decimal('0.01'))
        except InvalidOperation:
            raise ValidationError("Invalid deposit amount")

    def clean_contact(self):
        contact = str(self.cleaned_data.get('contact', '')).strip()
        if contact:
            contact = re.sub(r'[\s\-\(\)]', '', contact)
            if not MW_PHONE_REGEX.match(contact):
                raise ValidationError("Use: +265991234567 or 0991234567 or 0881234567")
            if contact.startswith('0'):
                contact = '+265' + contact[1:]
        return contact

    def clean_video(self):
        return ListingForm.clean_video(self)

    def clean_image(self):
        image: UploadedFile = self.cleaned_data.get('image')
        if not image:
            return image
        if image.size > MAX_IMAGE_SIZE:
            raise ValidationError(f"Image is {image.size / 1024 / 1024:.1f}MB. Max: 10MB")
        try:
            file_head = image.read(2048)
            image.seek(0)
            mime = magic.from_buffer(file_head, mime=True)
            if mime not in ALLOWED_IMAGE_TYPES:
                raise ValidationError("Only JPG, PNG, WebP images allowed")
        except Exception:
            raise ValidationError("Cannot verify image. File may be corrupted.")
        image.name = re.sub(r'[^a-zA-Z0-9._-]', '', image.name)[:100]
        return image