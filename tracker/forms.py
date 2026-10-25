"""Validated forms for trip management and GPX transfer."""

from django import forms

from .models import Trip
from .services.gpx_service import MAX_GPX_BYTES


class TripUpdateForm(forms.ModelForm):
    class Meta:
        model = Trip
        fields = ("title", "confirmed_transport_mode")
        widgets = {
            "title": forms.TextInput(attrs={"maxlength": 120}),
            "confirmed_transport_mode": forms.Select(),
        }


class GPXUploadForm(forms.Form):
    file = forms.FileField(
        label="Fichier GPX",
        widget=forms.ClearableFileInput(attrs={"accept": ".gpx,application/gpx+xml"}),
    )

    def clean_file(self):
        uploaded_file = self.cleaned_data["file"]
        if uploaded_file.size > MAX_GPX_BYTES:
            raise forms.ValidationError("Le fichier GPX ne peut pas dépasser 2 Mio.")
        if not uploaded_file.name.lower().endswith(".gpx"):
            raise forms.ValidationError("Sélectionnez un fichier avec l'extension .gpx.")
        return uploaded_file
