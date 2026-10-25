"""Préférences de mobilité (Profile) : page web + API DRF documentée Swagger."""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import translation
from drf_spectacular.utils import extend_schema
from rest_framework import generics, permissions

from .forms import ProfilePrefsForm
from .models import Profile
from .serializers import ProfileSerializer


def apply_language(response, language):
    """Mémorise la langue du profil dans le cookie lu par LocaleMiddleware."""
    if language in dict(settings.LANGUAGES):
        response.set_cookie(settings.LANGUAGE_COOKIE_NAME, language, max_age=60 * 60 * 24 * 365)
    return response


@login_required
def preferences_view(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfilePrefsForm(request.POST, instance=profile)
        if form.is_valid():
            profile = form.save()
            translation.activate(profile.language)
            messages.success(request, "Préférences enregistrées.")
            return apply_language(redirect('accounts:preferences'), profile.language)
    else:
        form = ProfilePrefsForm(instance=profile)
    return render(request, 'accounts/preferences.html', {'form': form})


@extend_schema(tags=['accounts'], summary="Préférences de mobilité de l'utilisateur connecté")
class APIPreferencesView(generics.RetrieveUpdateAPIView):
    serializer_class = ProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return Profile.objects.get_or_create(user=self.request.user)[0]
