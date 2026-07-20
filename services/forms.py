from django import forms
from.models import Worker, Skill
from django.utils.text import slugify

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class WorkerSignupForm(forms.ModelForm):
    # Skill with autocomplete + manual entry
    skill_name = forms.CharField(
        max_length=50,
        label='Skill',
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Electrician, Drone Repair, or type your own',
            'list': 'skill-options',
            'autocomplete': 'off'
        })
    )

    phone = forms.CharField(
        max_length=13,
        label='WhatsApp Number',
        widget=forms.TextInput(attrs={
            'placeholder': '+265991234567',
            'class': 'form-input'
        }),
        help_text='Customers will call or WhatsApp you on this number'
    )

    bio = forms.CharField(
        widget=forms.Textarea(attrs={
            'rows': 3,
            'placeholder': 'Example: 5 years fixing house wiring in Area 25. I do installations and repairs.',
            'class': 'form-textarea'
        }),
        required=False
    )

    # Multi-upload for work photos
    work_photos = MultipleFileField(
        required=False,
        label='Photos of Your Work',
        help_text='You can select multiple. Best 1 will be shown for now.'
    )

    class Meta:
        model = Worker
        fields = [
            'name', 'phone', 'location',
            'years_experience', 'bio', 'has_airtel_money',
            'photo', 'id_photo'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'John Banda'}),
            'location': forms.TextInput(attrs={'class': 'form-input', 'placeholder': 'Area 25, Lilongwe'}),
            'years_experience': forms.NumberInput(attrs={
                'class': 'form-input',
                'min': '0',
                'placeholder': '5'
            }),
            'photo': forms.FileInput(attrs={
                'accept': 'image/*',
                'capture': 'user' # Opens selfie camera on mobile
            }),
            'id_photo': forms.FileInput(attrs={
                'accept': 'image/*',
                'capture': 'environment' # Opens back camera
            }),
        }
        labels = {
            'years_experience': 'Years of Experience',
            'id_photo': 'National ID Photo - For verification only',
            'photo': 'Profile Photo - Customers see this',
            'has_airtel_money': 'I have Airtel Money to receive payments'
        }
        help_texts = {
            'id_photo': 'Upload front of National ID. We delete after verifying.',
            'photo': 'Clear photo of your face. Builds trust.',
            'years_experience': 'In Malawi, customers get free quotes. You get paid after work is done.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['id_photo'].required = True # Must verify ID
        # Pass existing skills to template for datalist
        self.existing_skills = Skill.objects.filter(is_active=True).exclude(
            name__in=['Electrician', 'Drone Repair', 'TV and Radio Repair', 'Tailor', 'Carpenter']
        ).values_list('name', flat=True)

    def clean_skill_name(self):
        """ Normalize to prevent duplicate skills"""
        skill_name = self.cleaned_data['skill_name'].strip()
        if not skill_name:
            raise forms.ValidationError("Please enter your skill.")
        return skill_name.title()

    def clean_phone(self):
        """Strict Malawi format"""
        phone = self.cleaned_data['phone'].replace(' ', '')
        if not phone.startswith('+265'):
            raise forms.ValidationError("Phone must start with +265")
        if len(phone)!= 13:
            raise forms.ValidationError("Phone must be +265 followed by 9 digits. Example: +265991234567")
        if not phone[4:].isdigit():
            raise forms.ValidationError("Phone must contain only numbers after +265")
        return phone

    def save(self, commit=True):
        worker = super().save(commit=False)

        # Get or create skill
        skill_name = self.cleaned_data['skill_name']
        skill, created = Skill.objects.get_or_create(
            name__iexact=skill_name,
            defaults={
                'name': skill_name,
                'slug': slugify(skill_name),
                'is_active': True
            }
        )
        worker.skill = skill

        # multiple-upload
        work_photos = self.cleaned_data.get('work_photos')
        if work_photos:
            if isinstance(work_photos, list):
                worker.work_photo = work_photos[0]
            else:
                worker.work_photo = work_photos

        if commit:
            worker.save()
        return worker

class WorkerFilterForm(forms.Form):
    # Added q for text search
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Search name, skill...'
        })
    )

    skill = forms.ModelChoiceField(
        queryset=Skill.objects.filter(is_active=True),
        required=False,
        empty_label="All Skills",
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    location = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-input',
            'placeholder': 'Area 23, Golgotha...'
        })
    )