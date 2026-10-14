"""
Vues de l'application Accounts (authentification, profil, HTMX et API DRF).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import CustomUser
from .forms import CustomUserCreationForm, CustomLoginForm, ProfileEditForm
from .serializers import UserSerializer, RegisterSerializer


def register_view(request):
    """Inscription d'un nouvel utilisateur avec profil éco."""
    if request.user.is_authenticated:
        return redirect('match:search')

    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
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
            login(request, user)
            messages.success(request, f"Ravi de vous revoir, {user.first_name or user.username} !")
            next_url = request.GET.get('next') or 'match:search'
            return redirect(next_url)
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


@login_required
def profile_edit_htmx(request):
    """
    Mise à jour dynamique du profil via HTMX sans rechargement de page.
    """
    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            user = form.save()
            messages.success(request, "Votre profil écologique a été mis à jour avec succès !")
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
