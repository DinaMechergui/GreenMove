"""Formulaires du module Traffic avec validation métier stricte côté serveur."""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import MonitoringPoint, TrafficSnapshot


class MonitoringPointForm(forms.ModelForm):
    """Formulaire pour les points de surveillance du trafic en Tunisie."""

    class Meta:
        model = MonitoringPoint
        fields = ['name', 'latitude', 'longitude', 'profile', 'is_active']
        labels = {
            'name': _('Nom du point'),
            'latitude': _('Latitude (°N)'),
            'longitude': _('Longitude (°E)'),
            'profile': _('Profil de trafic'),
            'is_active': _('Point actif pour la surveillance'),
        }
        help_texts = {
            'latitude': _('Doit se situer en Tunisie (entre 30.0°N et 38.0°N).'),
            'longitude': _('Doit se situer en Tunisie (entre 7.0°E et 12.0°E).'),
            'profile': _('Détermine les courbes horaires de pointe (matin, soir, axe majeur, etc.).'),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': _('Ex. Avenue Habib Bourguiba')}),
            'latitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '30.0', 'max': '38.0'}),
            'longitude': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.0001', 'min': '7.0', 'max': '12.0'}),
            'profile': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean_latitude(self):
        lat = self.cleaned_data.get('latitude')
        if lat is not None and not (30.0 <= lat <= 38.0):
            raise forms.ValidationError(
                _("La latitude doit être comprise entre 30.0 et 38.0 (territoire tunisien).")
            )
        return lat

    def clean_longitude(self):
        lon = self.cleaned_data.get('longitude')
        if lon is not None and not (7.0 <= lon <= 12.0):
            raise forms.ValidationError(
                _("La longitude doit être comprise entre 7.0 et 12.0 (territoire tunisien).")
            )
        return lon


class TrafficSnapshotForm(forms.ModelForm):
    """Formulaire pour la saisie ou mise à jour manuelle d'un snapshot de trafic."""

    class Meta:
        model = TrafficSnapshot
        fields = [
            'point', 'timestamp', 'current_speed', 'free_flow_speed',
            'congestion', 'precipitation_mm', 'is_holiday', 'source',
        ]
        labels = {
            'point': _('Point de surveillance'),
            'timestamp': _('Date et heure de la mesure'),
            'current_speed': _('Vitesse actuelle (km/h)'),
            'free_flow_speed': _('Vitesse fluide de référence (km/h)'),
            'congestion': _('Indice de congestion (0.0 à 1.0)'),
            'precipitation_mm': _('Précipitations (mm)'),
            'is_holiday': _('Jour férié'),
            'source': _('Source de la donnée'),
        }
        widgets = {
            'point': forms.Select(attrs={'class': 'form-select'}),
            'timestamp': forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'}),
            'current_speed': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'free_flow_speed': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '1'}),
            'congestion': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '1'}),
            'precipitation_mm': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0'}),
            'is_holiday': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'source': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean_congestion(self):
        congestion = self.cleaned_data.get('congestion')
        if congestion is not None and not (0.0 <= congestion <= 1.0):
            raise forms.ValidationError(_("La congestion doit être comprise entre 0.0 (fluide) et 1.0 (bloqué)."))
        return congestion

    def clean_precipitation_mm(self):
        precip = self.cleaned_data.get('precipitation_mm')
        if precip is not None and precip < 0:
            raise forms.ValidationError(_("La quantité de précipitations ne peut pas être négative."))
        return precip

    def clean_current_speed(self):
        speed = self.cleaned_data.get('current_speed')
        if speed is not None and speed < 0:
            raise forms.ValidationError(_("La vitesse actuelle doit être positive ou nulle."))
        return speed

    def clean_free_flow_speed(self):
        free_speed = self.cleaned_data.get('free_flow_speed')
        if free_speed is not None and free_speed <= 0:
            raise forms.ValidationError(_("La vitesse fluide doit être strictement positive."))
        return free_speed

    def clean(self):
        cleaned_data = super().clean()
        current_speed = cleaned_data.get('current_speed')
        free_flow_speed = cleaned_data.get('free_flow_speed')
        congestion = cleaned_data.get('congestion')

        if current_speed is not None and free_flow_speed is not None and free_flow_speed > 0:
            if current_speed > 1.1 * free_flow_speed:
                self.add_error(
                    'current_speed',
                    _("La vitesse actuelle (%(curr)s km/h) ne peut pas excéder 110%% de la vitesse fluide (%(free)s km/h).") % {
                        'curr': current_speed, 'free': free_flow_speed
                    }
                )

            if congestion is not None:
                expected_congestion = max(0.0, min(1.0, 1.0 - (current_speed / free_flow_speed)))
                if abs(congestion - expected_congestion) > 0.05:
                    self.add_error(
                        'congestion',
                        _("Incohérence physique : avec une vitesse actuelle de %(curr)s km/h et fluide de %(free)s km/h, "
                          "la congestion théorique est %(theo).2f (écart supérieur à 0.05 avec la valeur saisie %(val).2f).") % {
                            'curr': current_speed, 'free': free_flow_speed,
                            'theo': expected_congestion, 'val': congestion
                        }
                    )

        return cleaned_data
