"""
Vues de l'application Accounts (authentification, profil, HTMX et API DRF).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from django.views.decorators.http import require_POST
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .forms import CustomUserCreationForm, CustomLoginForm, ProfileEditForm, ProfilePrefsForm
from .serializers import UserSerializer, RegisterSerializer, ProfileSerializer
from .models import AuditLog, Profile
from django.conf import settings
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from .audit import log_event
from . import gdpr
from .permissions import IsAdminRole


def register_view(request):
    """Inscription d'un nouvel utilisateur avec profil éco."""
    if request.user.is_authenticated:
        return redirect('match:search')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Plusieurs backends configurés (ModelBackend + allauth) : backend explicite requis
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f"Bienvenue sur GreenMove, {user.first_name or user.username} ! Vous avez reçu 100 GreenPoints de bienvenue.")
            return redirect('accounts:profile')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = CustomUserCreationForm()

    return render(request, 'accounts/register.html', {'form': form})


def login_view(request):
    """Connexion d'un utilisateur."""
    if request.user.is_authenticated:
        return redirect('match:search')

    if request.method == 'POST':
        form = CustomLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user, backend=getattr(user, 'backend', None) or 'django.contrib.auth.backends.ModelBackend')
            messages.success(request, f"Ravi de vous revoir, {user.first_name or user.username} !")
            next_url = request.GET.get('next') or 'match:search'
            from .prefs_views import apply_language
            profile = Profile.objects.get_or_create(user=user)[0]
            return apply_language(redirect(next_url), profile.language)
        else:
            messages.error(request, "Identifiants invalides. Veuillez réessayer.")
    else:
        form = CustomLoginForm()

    return render(request, 'accounts/login.html', {'form': form})


def logout_view(request):
    """Déconnexion."""
    logout(request)
    messages.info(request, "Vous avez été déconnecté avec succès. À bientôt pour un trajet vert !")
    return redirect('core:home')


@login_required
def profile_view(request):
    """Affichage du tableau de bord et profil de mobilité de l'utilisateur."""
    user = request.user
    form = ProfileEditForm(instance=user)
    my_rides = user.rides.all().order_by('-departure_datetime')[:5]
    my_bookings = user.my_bookings.all().order_by('-created_at')[:5]

    context = {
        'user_profile': user,
        'form': form,
        'my_rides': my_rides,
        'my_bookings': my_bookings,
    }
    return render(request, 'accounts/profile.html', context)


def _sync_rides_with_profile(user, old_home: str, old_work: str) -> int:
    """
    Les trajets récurrents qui utilisaient les anciennes adresses du profil
    suivent les nouvelles (géocodage), puis les groupes DBSCAN sont recalculés :
    l'utilisateur est automatiquement déplacé vers le groupe de son nouveau trajet.
    Retourne le nombre de trajets mis à jour.
    """
    new_home = user.home_address or ''
    new_work = user.work_address or ''
    if not (old_home or old_work) or (old_home == new_home and old_work == new_work):
        return 0

    from match.models import Ride
    from match.services.geocoding import geocode_address

    changed = 0
    for ride in Ride.objects.filter(user=user, is_recurring=True):
        fields = []
        if old_home and new_home != old_home and ride.origin_address == old_home:
            ride.origin_address = new_home
            coords = geocode_address(new_home)
            if coords:
                ride.origin_lat, ride.origin_lon = coords
            fields += ['origin_address', 'origin_lat', 'origin_lon']
        if old_work and new_work != old_work and ride.destination_address == old_work:
            ride.destination_address = new_work
            coords = geocode_address(new_work)
            if coords:
                ride.destination_lat, ride.destination_lon = coords
            fields += ['destination_address', 'destination_lat', 'destination_lon']
        if fields:
            ride.save(update_fields=fields + ['updated_at'])
            changed += 1

    if changed:
        try:
            from match.services.clusters import compute_and_persist_groups
            compute_and_persist_groups()
        except Exception:
            pass
    return changed


@login_required
def profile_edit_htmx(request):
    """
    Mise à jour dynamique du profil via HTMX sans rechargement de page.
    """
    if request.method == 'POST':
        old_home = request.user.home_address
        old_work = request.user.work_address
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            updated = _sync_rides_with_profile(user, old_home, old_work)
            messages.success(request, "Votre profil écologique a été mis à jour avec succès !")
            if updated:
                messages.info(
                    request,
                    f"{updated} trajet(s) récurrent(s) aligné(s) sur vos nouvelles adresses : "
                    "vos groupes ont été recalculés automatiquement.",
                )
            return render(request, 'accounts/includes/profile_card.html', {'user_profile': user})
        else:
            return render(request, 'accounts/includes/profile_form.html', {'form': form})

    form = ProfileEditForm(instance=request.user)
    return render(request, 'accounts/includes/profile_form.html', {'form': form})


# ==========================================
# VUES API REST (DRF & SimpleJWT)
# ==========================================

class APIRegisterView(generics.CreateAPIView):
    """Endpoint REST pour créer un nouvel utilisateur."""
    queryset = CustomUser.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class APIProfileView(generics.RetrieveUpdateAPIView):
    """Endpoint REST pour consulter et modifier le profil connecté."""
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def perform_update(self, serializer):
        user = self.get_object()
        old_home, old_work = user.home_address, user.work_address
        serializer.save()
        _sync_rides_with_profile(user, old_home, old_work)


# ==========================================
# RGPD : export et suppression des données
# ==========================================

def _export_response(user, fmt, request):
    log_event(AuditLog.Action.DATA_EXPORT, user, detail=fmt, request=request)
    if fmt == 'zip':
        resp = HttpResponse(gdpr.export_zip_bytes(user), content_type='application/zip')
        resp['Content-Disposition'] = 'attachment; filename="greenmove_data.zip"'
    else:
        resp = HttpResponse(gdpr.export_json_bytes(user), content_type='application/json')
        resp['Content-Disposition'] = 'attachment; filename="greenmove_data.json"'
    return resp


@login_required
def export_data_view(request):
    """Téléchargement des données personnelles (?format=json|zip)."""
    fmt = 'zip' if request.GET.get('format') == 'zip' else 'json'
    return _export_response(request.user, fmt, request)


@login_required
@require_POST
def delete_account_view(request):
    """Suppression du compte avec anonymisation (confirmation par mot de passe)."""
    if not request.user.check_password(request.POST.get('password', '')):
        messages.error(request, "Mot de passe incorrect : le compte n'a pas été supprimé.")
        return redirect('accounts:profile')
    user = request.user
    log_event(AuditLog.Action.ACCOUNT_DELETE, user, request=request)
    logout(request)
    gdpr.delete_account(user)
    messages.info(request, "Votre compte a été supprimé et vos données anonymisées.")
    return redirect('core:home')


class APIExportDataView(APIView):
    """Export RGPD de l'utilisateur connecté (JSON ou ZIP via ?format=zip)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        fmt = 'zip' if request.query_params.get('export') == 'zip' else 'json'
        return _export_response(request.user, fmt, request._request)


class APIDeleteAccountView(APIView):
    """Suppression du compte connecté (corps : {"password": "..."})."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        if not request.user.check_password(request.data.get('password', '')):
            return Response({'detail': 'Mot de passe incorrect.'}, status=status.HTTP_403_FORBIDDEN)
        log_event(AuditLog.Action.ACCOUNT_DELETE, request.user, request=request._request)
        gdpr.delete_account(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class APIAuditLogView(generics.ListAPIView):
    """Journal d'audit complet (réservé au rôle Admin)."""
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return AuditLog.objects.select_related('user')[:200]

    def list(self, request, *args, **kwargs):
        rows = [
            {'at': a.created_at, 'user': a.username, 'action': a.action, 'detail': a.detail, 'ip': a.ip_address}
            for a in self.get_queryset()
        ]
        return Response(rows)
