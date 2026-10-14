"""
Modèles pour l'application MobilityMatch AI.
Gère les propositions de trajets, les demandes et les réservations de covoiturage vert.
"""
from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _
import json
import math


class Ride(models.Model):
    """
    Trajet proposé (offre de conducteur) ou recherché (demande de passager).
    """
    class RideTypeChoices(models.TextChoices):
        OFFER = 'OFFER', _('Proposition de trajet (Conducteur)')
        REQUEST = 'REQUEST', _('Recherche de trajet (Passager)')

    class StatusChoices(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Actif / Disponible')
        FULL = 'FULL', _('Complet')
        COMPLETED = 'COMPLETED', _('Terminé')
        CANCELLED = 'CANCELLED', _('Annulé')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='rides',
        verbose_name=_('Créateur du trajet')
    )
    ride_type = models.CharField(
        _('Type de trajet'),
        max_length=10,
        choices=RideTypeChoices.choices,
        default=RideTypeChoices.OFFER
    )
    status = models.CharField(
        _('Statut'),
        max_length=15,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE
    )

    # Point de départ
    origin_address = models.CharField(_('Adresse de départ'), max_length=255)
    origin_lat = models.FloatField(_('Latitude départ'))
    origin_lon = models.FloatField(_('Longitude départ'))

    # Point d'arrivée
    destination_address = models.CharField(_('Adresse d\'arrivée'), max_length=255)
    destination_lat = models.FloatField(_('Latitude arrivée'))
    destination_lon = models.FloatField(_('Longitude arrivée'))

    departure_datetime = models.DateTimeField(_('Date et heure de départ'))
    seats_available = models.PositiveSmallIntegerField(_('Places disponibles'), default=3)
    price_tnd = models.DecimalField(_('Partage de frais éco (DT)'), max_digits=6, decimal_places=2, default=0.0)

    # Trajet récurrent (ex: navetteurs quotidiens)
    is_recurring = models.BooleanField(_('Trajet régulier / domicile-travail'), default=False)
    recurring_days = models.CharField(_('Jours récurrents'), max_length=100, blank=True, help_text=_('Ex: Lun,Mar,Mer,Jeu,Ven'))

    description = models.TextField(_('Précisions sur le trajet'), blank=True)
    route_polyline = models.TextField(
        _('Tracé routier (JSON)'),
        blank=True,
        default='[]',
        help_text=_('Polyline [lat, lon] utilisée pour le calcul de similarité de trajectoire.')
    )
    created_at = models.DateTimeField(_('Date de création'), auto_now_add=True)
    updated_at = models.DateTimeField(_('Dernière mise à jour'), auto_now=True)

    class Meta:
        verbose_name = _('Trajet Covoiturage')
        verbose_name_plural = _('Trajets Covoiturage')
        ordering = ['departure_datetime']

    def __str__(self):
        return f"[{self.get_ride_type_display()}] {self.origin_address} ➔ {self.destination_address} ({self.departure_datetime.strftime('%d/%m %H:%M')})"

    @property
    def distance_km(self) -> float:
        """
        Calcule la distance géodésique (Haversine) approximative en kilomètres.
        """
        r = 6371.0  # Rayon terrestre moyen en km
        d_lat = math.radians(self.destination_lat - self.origin_lat)
        d_lon = math.radians(self.destination_lon - self.origin_lon)
        lat1 = math.radians(self.origin_lat)
        lat2 = math.radians(self.destination_lat)

        a = math.sin(d_lat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(d_lon / 2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return round(r * c, 1)

    @property
    def estimated_co2_saved(self) -> float:
        """
        Calcule l'économie de CO2 estimée (en kg) par passager.
        Basé sur une moyenne de ~130g CO2/km évitée par rapport à une voiture individuelle.
        """
        return round(self.distance_km * 0.13, 2)

    @property
    def polyline_coords(self) -> list:
        """Retourne le tracé du trajet sous forme de liste [[lat, lon], ...]."""
        try:
            data = json.loads(self.route_polyline or '[]')
            return data if isinstance(data, list) else []
        except (ValueError, TypeError):
            return []


class RideBooking(models.Model):
    """
    Demande de réservation ou de contact pour un trajet de covoiturage.
    """
    class StatusChoices(models.TextChoices):
        PENDING = 'PENDING', _('En attente')
        ACCEPTED = 'ACCEPTED', _('Accepté')
        REJECTED = 'REJECTED', _('Refusé')
        CANCELLED = 'CANCELLED', _('Annulé')

    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='bookings',
        verbose_name=_('Trajet associé')
    )
    passenger = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='my_bookings',
        verbose_name=_('Passager demandeur')
    )
    status = models.CharField(
        _('Statut de la demande'),
        max_length=15,
        choices=StatusChoices.choices,
        default=StatusChoices.PENDING
    )
    seats_requested = models.PositiveSmallIntegerField(_('Places demandées'), default=1)
    message = models.TextField(_('Message au conducteur'), blank=True)
    created_at = models.DateTimeField(_('Date de demande'), auto_now_add=True)

    class Meta:
        verbose_name = _('Réservation de Trajet')
        verbose_name_plural = _('Réservations de Trajets')
        ordering = ['-created_at']

    def __str__(self):
        return f"Réservation par {self.passenger} sur trajet #{self.ride_id} ({self.get_status_display()})"


class Review(models.Model):
    """
    Avis post-trajet : alimente le score de fiabilité (reliability_score) du profil.
    """
    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='reviews',
        verbose_name=_('Trajet concerné')
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_written',
        verbose_name=_('Auteur de l\'avis')
    )
    reviewed_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='reviews_received',
        verbose_name=_('Utilisateur évalué')
    )
    rating = models.PositiveSmallIntegerField(_('Note (1-5)'))
    comment = models.TextField(_('Commentaire'), blank=True)
    created_at = models.DateTimeField(_('Date de l\'avis'), auto_now_add=True)

    class Meta:
        verbose_name = _('Avis de Trajet')
        verbose_name_plural = _('Avis de Trajets')
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['ride', 'reviewer'], name='unique_review_per_ride_and_reviewer'),
            models.CheckConstraint(condition=models.Q(rating__gte=1, rating__lte=5), name='rating_between_1_and_5'),
        ]

    def __str__(self):
        return f"{self.rating}/5 par {self.reviewer} → {self.reviewed_user} (trajet #{self.ride_id})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Recalcul du score de fiabilité de l'utilisateur évalué
        ratings = Review.objects.filter(reviewed_user=self.reviewed_user).values_list('rating', flat=True)
        ratings = list(ratings)
        if ratings:
            self.reviewed_user.reliability_score = round(sum(ratings) / len(ratings), 2)
            self.reviewed_user.save(update_fields=['reliability_score'])


class ChatRoom(models.Model):
    """
    Salon de discussion temps réel associé à une réservation de trajet.
    """
    ride = models.OneToOneField(
        Ride,
        on_delete=models.CASCADE,
        related_name='chat_room',
        verbose_name=_('Trajet')
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='chat_rooms',
        verbose_name=_('Participants')
    )
    created_at = models.DateTimeField(_('Création'), auto_now_add=True)

    class Meta:
        verbose_name = _('Salon de Discussion')
        verbose_name_plural = _('Salons de Discussion')

    def __str__(self):
        return f"Chat trajet #{self.ride_id}"


class ChatMessage(models.Model):
    """
    Message de chat. sender=NULL ⇒ message système / suggestion d'accueil.
    """
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name=_('Salon')
    )
    sender = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='chat_messages',
        null=True,
        blank=True,
        verbose_name=_('Expéditeur')
    )
    content = models.TextField(_('Contenu'))
    is_suggestion = models.BooleanField(_('Suggestion d\'accueil'), default=False)
    created_at = models.DateTimeField(_('Date d\'envoi'), auto_now_add=True)

    class Meta:
        verbose_name = _('Message de Chat')
        verbose_name_plural = _('Messages de Chat')
        ordering = ['created_at']

    def __str__(self):
        author = self.sender.username if self.sender else 'Système'
        return f"[{author}] {self.content[:40]}"


class TrackingLink(models.Model):
    """
    Lien de suivi live partagé (token UUID, expiration 24h).
    """
    ride = models.ForeignKey(
        Ride,
        on_delete=models.CASCADE,
        related_name='tracking_links',
        verbose_name=_('Trajet suivi')
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tracking_links',
        verbose_name=_('Créateur du lien')
    )
    token = models.UUIDField(_('Token unique'), unique=True, editable=False)
    is_active = models.BooleanField(_('Actif'), default=True)
    expires_at = models.DateTimeField(_('Expire le'))
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Lien de Suivi Live')
        verbose_name_plural = _('Liens de Suivi Live')

    def __str__(self):
        return f"Suivi live trajet #{self.ride_id} ({'actif' if self.is_active else 'inactif'})"

    @property
    def is_valid(self) -> bool:
        from django.utils import timezone
        return self.is_active and (self.expires_at is None or self.expires_at > timezone.now())


class SOSAlert(models.Model):
    """
    Alertes de sécurité déclenchées par un utilisateur pendant un trajet.
    """
    class StatusChoices(models.TextChoices):
        ACTIVE = 'ACTIVE', _('Active')
        RESOLVED = 'RESOLVED', _('Résolue')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='sos_alerts',
        verbose_name=_('Utilisateur en danger')
    )
    ride = models.ForeignKey(
        Ride,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sos_alerts',
        verbose_name=_('Trajet concerné')
    )
    latitude = models.FloatField(_('Latitude'), null=True, blank=True)
    longitude = models.FloatField(_('Longitude'), null=True, blank=True)
    message = models.TextField(_('Message'), blank=True)
    status = models.CharField(
        _('Statut'),
        max_length=10,
        choices=StatusChoices.choices,
        default=StatusChoices.ACTIVE
    )
    created_at = models.DateTimeField(_('Déclenchée le'), auto_now_add=True)
    resolved_at = models.DateTimeField(_('Résolue le'), null=True, blank=True)

    class Meta:
        verbose_name = _('Alerte SOS')
        verbose_name_plural = _('Alertes SOS')
        ordering = ['-created_at']

    def __str__(self):
        return f"SOS de {self.user} ({self.get_status_display()})"


class RideGroup(models.Model):
    """
    Groupe de trajets récurrents issu du clustering DBSCAN
    (covoiturage, pédibus ou convoi vélo).
    """
    class ModeChoices(models.TextChoices):
        COVOITURAGE = 'COVOITURAGE', _('Covoiturage')
        PEDIBUS = 'PEDIBUS', _('Pédibus')
        CONVOI_VELO = 'CONVOI_VELO', _('Convoi vélo / trottinette')

    cluster_id = models.IntegerField(_('Identifiant de cluster DBSCAN'))
    mode = models.CharField(_('Mode suggéré'), max_length=15, choices=ModeChoices.choices)
    label = models.CharField(_('Libellé'), max_length=200)
    origin_lat = models.FloatField(_('Latitude centroid départ'))
    origin_lon = models.FloatField(_('Longitude centroid départ'))
    destination_lat = models.FloatField(_('Latitude centroid arrivée'))
    destination_lon = models.FloatField(_('Longitude centroid arrivée'))
    rides = models.ManyToManyField(
        Ride,
        related_name='ride_groups',
        verbose_name=_('Trajets du groupe')
    )
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='ride_groups',
        verbose_name=_('Membres')
    )
    created_at = models.DateTimeField(_('Créé le'), auto_now_add=True)

    class Meta:
        verbose_name = _('Groupe de Trajets')
        verbose_name_plural = _('Groupes de Trajets')
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.get_mode_display()}] {self.label} (cluster #{self.cluster_id})"
