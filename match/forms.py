"""
Formulaires pour l'application MobilityMatch.
"""
from django import forms
from django.utils import timezone
from .models import Ride, RideBooking, Review


class RideCreationForm(forms.ModelForm):
    """Formulaire de publication d'un trajet de covoiturage vert."""
    departure_date = forms.DateField(
        label="Date du départ",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        initial=timezone.now().date
    )
    departure_time_input = forms.TimeInput(
        attrs={'type': 'time', 'class': 'form-control'},
    )

    class Meta:
        model = Ride
        fields = (
            'ride_type',
            'origin_address',
            'destination_address',
            'seats_available',
            'price_tnd',
            'is_recurring',
            'recurring_days',
            'description',
        )
        widgets = {
            'origin_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ariana Centre, Station Métro 2'}),
            'destination_address': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Les Berges du Lac 2, Tunis'}),
            'seats_available': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 6}),
            'price_tnd': forms.NumberInput(attrs={'class': 'form-control', 'step': 0.5, 'min': 0}),
            'recurring_days': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Lun, Mar, Mer, Jeu, Ven'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Précisions utiles (climatisation douce, bagages, lieu de rdv précis)...'}),
            'ride_type': forms.Select(attrs={'class': 'form-select'}),
            'is_recurring': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }


class RideSearchForm(forms.Form):
    """Formulaire de recherche intelligente de covoiturage vert."""
    origin = forms.CharField(
        label="Lieu de départ",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Ariana, Le Bardo, Centre-ville...'})
    )
    destination = forms.CharField(
        label="Lieu d'arrivée",
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Lac 2, Manouba, Marsa...'})
    )
    ride_type = forms.ChoiceField(
        label="Type",
        required=False,
        choices=[('', 'Tous les trajets'), ('OFFER', 'Offres de covoiturage'), ('REQUEST', 'Demandes de passagers')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    only_green_vehicles = forms.BooleanField(
        label="Véhicules 100% Électriques / Hybrides uniquement",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )


class BookingForm(forms.ModelForm):
    """Formulaire de demande de réservation de trajet."""
    class Meta:
        model = RideBooking
        fields = ('seats_requested', 'message')
        widgets = {
            'seats_requested': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 4, 'value': 1}),
            'message': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Ex: Bonjour ! Je vous attendrai au rond-point.'}),
        }


class ReviewForm(forms.ModelForm):
    """Avis post-trajet : note 1-5 et commentaire."""
    RATING_CHOICES = [(i, f"{'★' * i}{'☆' * (5 - i)} ({i}/5)") for i in range(5, 0, -1)]

    rating = forms.TypedChoiceField(
        label="Votre note",
        choices=RATING_CHOICES,
        coerce=int,
        initial=5,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    comment = forms.CharField(
        label="Commentaire (optionnel)",
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Ponctualité, partage, convivialité...',
        }),
    )

    class Meta:
        model = Review
        fields = ('rating', 'comment')


class SplitCalculatorForm(forms.Form):
    """Calculateur de partage des frais & CO₂ (duo ou groupe)."""
    ride = forms.ModelChoiceField(
        label="Trajet (optionnel)",
        queryset=Ride.objects.all().order_by('-departure_datetime'),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    distance_km = forms.FloatField(
        label="Distance (km)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 0.1, 'placeholder': 'Ex: 12.5'}),
    )
    passengers = forms.IntegerField(
        label="Nombre de personnes",
        required=False,
        min_value=1,
        max_value=12,
        initial=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'max': 12}),
    )
    total_cost = forms.FloatField(
        label="Montant à partager (DT, optionnel)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': 0.1, 'placeholder': 'Ex: 15'}),
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('ride') and not cleaned.get('distance_km'):
            raise forms.ValidationError("Sélectionnez un trajet ou saisissez une distance.")
        return cleaned
