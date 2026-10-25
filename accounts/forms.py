"""
Formulaires pour l'authentification et la gestion du profil éco-mobilité.
"""
from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import CustomUser, Profile


class CustomUserCreationForm(UserCreationForm):
    """
    Formulaire d'inscription intégrant les préférences de mobilité écologique.
    """
    first_name = forms.CharField(label="Prénom", max_length=50, required=True)
    last_name = forms.CharField(label="Nom de famille", max_length=50, required=True)
    email = forms.EmailField(label="Adresse email", required=True)
    home_address = forms.CharField(label="Adresse de domicile (ex: Ariana)", max_length=255, required=False)
    work_address = forms.CharField(label="Adresse de travail (ex: Lac 2)", max_length=255, required=False)

    class Meta:
        model = CustomUser
        fields = (
            'username',
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'role',
            'vehicle_type',
            'vehicle_model',
            'available_seats',
            'home_address',
            'work_address',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'form-control rounded-pill-sm'})


class CustomLoginForm(AuthenticationForm):
    """Formulaire de connexion stylisé."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Nom d\'utilisateur ou email'})
        self.fields['password'].widget.attrs.update({'class': 'form-control', 'placeholder': 'Mot de passe'})


class ProfileEditForm(forms.ModelForm):
    """Formulaire d'édition du profil en direct (HTMX ou standard)."""
    class Meta:
        model = CustomUser
        fields = (
            'first_name',
            'last_name',
            'email',
            'phone_number',
            'bio',
            'role',
            'vehicle_type',
            'vehicle_model',
            'available_seats',
            'home_address',
            'home_lat',
            'home_lon',
            'work_address',
            'work_lat',
            'work_lon',
            'departure_time_default',
            'gender',
            'is_smoker',
            'ride_preference',
        )
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'departure_time_default': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'gender': forms.Select(attrs={'class': 'form-select'}),
            'ride_preference': forms.Select(attrs={'class': 'form-select'}),
            'is_smoker': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        custom_classed = ('bio', 'departure_time_default', 'gender', 'ride_preference', 'is_smoker')
        for name, field in self.fields.items():
            if name != 'email':
                field.required = False
            if name in custom_classed:
                continue
            field.widget.attrs.update({'class': 'form-control'})


class ProfilePrefsForm(forms.ModelForm):
    """Préférences de mobilité (ville, mode préféré, objectif carbone, langue)."""

    class Meta:
        model = Profile
        fields = ('city', 'preferred_mode', 'carbon_goal_kg', 'language')
        widgets = {
            'city': forms.TextInput(attrs={'class': 'form-control'}),
            'preferred_mode': forms.Select(attrs={'class': 'form-select'}),
            'carbon_goal_kg': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': 1}),
            'language': forms.Select(attrs={'class': 'form-select'}),
        }
