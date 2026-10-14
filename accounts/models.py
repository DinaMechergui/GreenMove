"""
Modèles pour l'application Accounts.
Définit le CustomUser enrichi pour l'éco-mobilité dans le Grand Tunis.
"""
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.utils.translation import gettext_lazy as _


class CustomUser(AbstractUser):
    """
    Modèle utilisateur personnalisé intégrant le profil de mobilité durable.
    """
    class RoleChoices(models.TextChoices):
        DRIVER = 'DRIVER', _('Conducteur')
        PASSENGER = 'PASSENGER', _('Passager')
        BOTH = 'BOTH', _('Les deux (Mixte)')

    class VehicleChoices(models.TextChoices):
        ELECTRIC = 'ELECTRIC', _('Véhicule 100% Électrique (Zéro Émission)')
        HYBRID = 'HYBRID', _('Véhicule Hybride')
        THERMAL_ECO = 'THERMAL_ECO', _('Thermique éco-efficient (< 110g CO2/km)')
        BICYCLE_SCOOTER = 'BICYCLE_SCOOTER', _('Vélo / Trottinette électrique')
        NONE = 'NONE', _('Aucun véhicule personnel')

    class GenderChoices(models.TextChoices):
        MALE = 'M', _('Homme')
        FEMALE = 'F', _('Femme')
        OTHER = 'OTHER', _('Autre / Préfère ne pas dire')

    class RidePreferenceChoices(models.TextChoices):
        MIXTE = 'MIXTE', _('Trajet mixte (tous)')
        WOMEN_ONLY = 'WOMEN_ONLY', _('Femmes uniquement')

    email = models.EmailField(_('Adresse email'), unique=True)
    phone_number = models.CharField(_('Numéro de téléphone'), max_length=20, blank=True)
    role = models.CharField(
        _('Rôle de mobilité'),
        max_length=20,
        choices=RoleChoices.choices,
        default=RoleChoices.PASSENGER
    )
    vehicle_type = models.CharField(
        _('Type de véhicule'),
        max_length=25,
        choices=VehicleChoices.choices,
        default=VehicleChoices.NONE
    )
    vehicle_model = models.CharField(_('Modèle de véhicule'), max_length=100, blank=True)
    available_seats = models.PositiveSmallIntegerField(_('Places disponibles par trajet'), default=3)
    eco_points = models.IntegerField(_('Points écologiques'), default=100)
    avatar = models.ImageField(_('Photo de profil'), upload_to='avatars/', blank=True, null=True)
    bio = models.TextField(_('Biographie / Présentation'), blank=True)

    # Localisation domicile-travail (Grand Tunis)
    home_address = models.CharField(_('Adresse de domicile'), max_length=255, blank=True)
    home_lat = models.FloatField(_('Latitude domicile'), null=True, blank=True)
    home_lon = models.FloatField(_('Longitude domicile'), null=True, blank=True)

    work_address = models.CharField(_('Adresse de travail / université'), max_length=255, blank=True)
    work_lat = models.FloatField(_('Latitude travail'), null=True, blank=True)
    work_lon = models.FloatField(_('Longitude travail'), null=True, blank=True)

    departure_time_default = models.TimeField(_('Heure de départ habituelle'), null=True, blank=True)

    # Préférences de covoiturage & sécurité (MobilityMatch)
    gender = models.CharField(
        _('Genre'),
        max_length=10,
        choices=GenderChoices.choices,
        blank=True,
    )
    is_smoker = models.BooleanField(_('Fumeur / fumeuse'), default=False)
    ride_preference = models.CharField(
        _('Préférence de trajet'),
        max_length=15,
        choices=RidePreferenceChoices.choices,
        default=RidePreferenceChoices.MIXTE,
    )
    profile_verified = models.BooleanField(_('Profil vérifié'), default=False)
    verified_at = models.DateTimeField(_('Date de vérification'), null=True, blank=True)
    reliability_score = models.FloatField(_('Score de fiabilité (avis)'), default=5.0)

    class Meta:
        verbose_name = _('Utilisateur GreenMove')
        verbose_name_plural = _('Utilisateurs GreenMove')

    def __str__(self):
        full_name = self.get_full_name()
        return full_name if full_name else self.username

    @property
    def eco_badge(self) -> str:
        """Détermine le badge écologique selon l'activité et le véhicule."""
        if self.vehicle_type == self.VehicleChoices.ELECTRIC:
            return "Zéro Émission"
        elif self.eco_points >= 500:
            return "Champion Vert Tunis"
        elif self.eco_points >= 250:
            return "Pionnier Éco"
        elif self.vehicle_type == self.VehicleChoices.HYBRID:
            return "Navetteur Hybride"
        return "Éco-Adhérent"

    @property
    def co2_saved_kg(self) -> float:
        """Estimation approximative du CO2 économisé (en kg)."""
        return round(self.eco_points * 0.45, 1)

    def get_avatar_url(self) -> str:
        """Retourne l'URL de l'avatar ou un avatar par défaut stylisé."""
        if self.avatar:
            return self.avatar.url
        # Générateur d'avatar déterministe et élégant
        return f"https://api.dicebear.com/7.x/bottts/svg?seed={self.username}&backgroundColor=b6e3f4,c0aede,d1d4f9,ffd5dc,ffdfbf"
