"""
Modèles pour l'application EcoRewards & Gamification (GreenMove).
Gère :
- Profils de gamification & niveaux (Graine Verte -> Légende Carbone Zéro)
- Registre des transactions éco-points et CO2 réellement économisé
- Badges et critères de déblocage
- Défis personnalisés par IA (clustering KMeans) à difficulté progressive
- Défis collectifs inter-entreprises, universités et quartiers (jauges)
- Boutique de récompenses partenaires, coupons et QR codes validables
"""
import uuid
import math
from datetime import date, timedelta
from django.db import models
from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class UserGamificationProfile(models.Model):
    """
    Profil d'éco-gamification étendu rattaché à chaque CustomUser.
    Centralise les points, les niveaux, les statistiques d'émissions et le profilage IA KMeans.
    """
    LEVEL_THRESHOLDS = [
        (1, 0, 250, "Graine Verte", "bi-seedling", "#84A98C"),
        (2, 251, 600, "Jeune Pousse", "bi-flower1", "#52796F"),
        (3, 601, 1200, "Éco-Navetteur", "bi-bicycle", "#335C45"),
        (4, 1201, 2500, "Gardien du Climat", "bi-shield-shaded", "#0284C7"),
        (5, 2501, 999999, "Légende Carbone Zéro", "bi-trophy-fill", "#E9C46A"),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='gamification_profile',
        verbose_name=_('Utilisateur')
    )
    total_co2_saved_kg = models.FloatField(_('CO₂ total évité (kg)'), default=0.0)
    monthly_co2_saved_kg = models.FloatField(_('CO₂ évité ce mois (kg)'), default=0.0)
    streak_days = models.PositiveIntegerField(_('Série de jours éco-actifs consécutifs'), default=1)
    last_activity_date = models.DateField(_('Date de dernière activité'), default=timezone.now)

    # Segmentation pour classements par quartier ou établissement
    district = models.CharField(
        _('Quartier / Délégation Grand Tunis'),
        max_length=100,
        blank=True,
        default='Les Berges du Lac 2',
        help_text=_('Ex: Lac 2, Ariana, La Marsa, Le Bardo, Centre-ville, Ennasr')
    )
    organization = models.CharField(
        _('Établissement / Entreprise / Université'),
        max_length=120,
        blank=True,
        default='ESPRIT',
        help_text=_('Ex: ESPRIT, INSAT, Université de Tunis, Telnet, Vermeg')
    )

    # Profil comportemental issu du modèle de clustering KMeans
    kmeans_cluster = models.IntegerField(_('Cluster KMeans'), default=0)
    kmeans_cluster_label = models.CharField(
        _('Profil comportemental IA'),
        max_length=80,
        default='Navetteur Quotidien'
    )
    last_profiled_at = models.DateTimeField(_('Dernier profilage IA'), auto_now_add=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Profil Éco-Gamification')
        verbose_name_plural = _('Profils Éco-Gamification')

    def __str__(self):
        return f"Gamification ({self.user.username}) - {self.current_level_name} ({self.user.eco_points} pts)"

    @property
    def current_points(self) -> int:
        return self.user.eco_points

    @property
    def current_level_info(self):
        pts = self.current_points
        for lvl, min_pts, max_pts, title, icon, color in self.LEVEL_THRESHOLDS:
            if min_pts <= pts <= max_pts:
                return {
                    'level': lvl,
                    'min_pts': min_pts,
                    'max_pts': max_pts,
                    'title': title,
                    'icon': icon,
                    'color': color,
                }
        return {
            'level': 5,
            'min_pts': 2501,
            'max_pts': 999999,
            'title': "Légende Carbone Zéro",
            'icon': "bi-trophy-fill",
            'color': "#E9C46A",
        }

    @property
    def current_level(self) -> int:
        return self.current_level_info['level']

    @property
    def current_level_name(self) -> str:
        return self.current_level_info['title']

    @property
    def current_level_icon(self) -> str:
        return self.current_level_info['icon']

    @property
    def current_level_color(self) -> str:
        return self.current_level_info['color']

    @property
    def next_level_threshold(self) -> int:
        info = self.current_level_info
        return info['max_pts'] + 1 if info['level'] < 5 else info['max_pts']

    @property
    def points_to_next_level(self) -> int:
        info = self.current_level_info
        if info['level'] >= 5:
            return 0
        return max(0, (info['max_pts'] + 1) - self.current_points)

    @property
    def level_progress_percent(self) -> int:
        info = self.current_level_info
        if info['level'] >= 5:
            return 100
        span = info['max_pts'] - info['min_pts'] + 1
        current = self.current_points - info['min_pts']
        progress = int((current / span) * 100)
        return max(5, min(100, progress))

    @property
    def trees_equivalent(self) -> float:
        """1 arbre moyen absorbe environ 21.77 kg de CO2 par an."""
        return round(self.total_co2_saved_kg / 21.77, 1)


class Badge(models.Model):
    """
    Badges éco-responsables à débloquer selon la progression de l'utilisateur.
    """
    class CategoryChoices(models.TextChoices):
        CO2 = 'CO2', _('Impact Carbone (CO₂)')
        RIDES = 'RIDES', _('Covoiturage & Trajets')
        STREAK = 'STREAK', _('Régularité & Fidélité')
        CHALLENGE = 'CHALLENGE', _('Défis Réussis')
        COMMUNITY = 'COMMUNITY', _('Collectif & Partage')

    class ThresholdTypeChoices(models.TextChoices):
        CO2_KG = 'CO2_KG', _('kg de CO₂ évités')
        RIDES_COUNT = 'RIDES_COUNT', _('Nombre de trajets complétés')
        POINTS = 'POINTS', _('Points cumulés')
        STREAK_DAYS = 'STREAK_DAYS', _('Jours consécutifs')
        COUPONS_USED = 'COUPONS_USED', _('Coupons récompensés')

    slug = models.SlugField(_('Identifiant unique (slug)'), unique=True)
    name = models.CharField(_('Nom du badge'), max_length=100)
    description = models.TextField(_('Description et condition de déblocage'))
    icon = models.CharField(_('Icône Bootstrap Icons'), max_length=60, default='bi-award-fill')
    badge_color = models.CharField(_('Couleur thématique (hex)'), max_length=30, default='#335C45')
    category = models.CharField(_('Catégorie'), max_length=30, choices=CategoryChoices.choices, default=CategoryChoices.CO2)
    threshold_type = models.CharField(_('Type de seuil'), max_length=30, choices=ThresholdTypeChoices.choices)
    threshold_value = models.FloatField(_('Valeur seuil'), default=1.0)
    points_reward = models.PositiveIntegerField(_('Points bonus attribués'), default=100)

    class Meta:
        verbose_name = _('Badge')
        verbose_name_plural = _('Badges')
        ordering = ['threshold_value']

    def __str__(self):
        return f"[{self.get_category_display()}] {self.name}"


class UserBadge(models.Model):
    """
    Association d'un badge débloqué par un utilisateur.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='earned_badges')
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE, related_name='holders')
    earned_at = models.DateTimeField(auto_now_add=True)
    is_viewed = models.BooleanField(default=False)

    class Meta:
        verbose_name = _('Badge Utilisateur')
        verbose_name_plural = _('Badges Utilisateurs')
        unique_together = ('user', 'badge')
        ordering = ['-earned_at']

    def __str__(self):
        return f"{self.user.username} 🏆 {self.badge.name} ({self.earned_at.strftime('%d/%m/%Y')})"


class EcoTransaction(models.Model):
    """
    Livre journalier immuable traçant chaque gain ou dépense d'éco-points
    et l'économie exacte de CO2 correspondante.
    """
    class TransactionTypeChoices(models.TextChoices):
        RIDE_DRIVER = 'RIDE_DRIVER', _('Trajet Covoiturage Conducteur')
        RIDE_PASSENGER = 'RIDE_PASSENGER', _('Trajet Covoiturage Passager')
        CHALLENGE_REWARD = 'CHALLENGE_REWARD', _('Défi Éco Réussi')
        BADGE_UNLOCK = 'BADGE_UNLOCK', _('Badge Débloqué')
        COUPON_REDEEM = 'COUPON_REDEEM', _('Échange Coupon Partenaire')
        STREAK_BONUS = 'STREAK_BONUS', _('Bonus Série Verte')
        ADMIN_GRANT = 'ADMIN_GRANT', _('Attribution Admin / Démo')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='eco_transactions',
        verbose_name=_('Utilisateur')
    )
    points = models.IntegerField(_('Éco-points (variation)'), help_text=_('+ pour un gain, - pour une dépense'))
    co2_saved_kg = models.FloatField(_('CO₂ évité (kg)'), default=0.0)
    transaction_type = models.CharField(_('Type'), max_length=30, choices=TransactionTypeChoices.choices)
    ride = models.ForeignKey(
        'match.Ride',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reward_transactions',
        verbose_name=_('Trajet associé (optionnel)')
    )
    description = models.CharField(_('Détails de l\'action'), max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Transaction Éco-Points')
        verbose_name_plural = _('Transactions Éco-Points')
        ordering = ['-created_at']

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{self.user.username} : {sign}{self.points} pts ({self.co2_saved_kg} kg CO₂) - {self.description}"


class PersonalizedChallenge(models.Model):
    """
    Défis personnalisés générés par l'IA selon le profil de mobilité (KMeans)
    avec difficulté progressive (Facile -> Moyen -> Expert).
    """
    class DifficultyChoices(models.TextChoices):
        EASY = 'EASY', _('Étape 1 : Facile')
        MEDIUM = 'MEDIUM', _('Étape 2 : Intermédiaire')
        HARD = 'HARD', _('Étape 3 : Expert')

    class StatusChoices(models.TextChoices):
        ACTIVE = 'ACTIVE', _('En cours')
        COMPLETED = 'COMPLETED', _('Accompli (À réclamer)')
        CLAIMED = 'CLAIMED', _('Récompensé')
        EXPIRED = 'EXPIRED', _('Expiré')

    class CategoryChoices(models.TextChoices):
        CO2 = 'CO2', _('Économie de CO₂')
        RIDES = 'RIDES', _('Partage de Trajets')
        PEAK_HOURS = 'PEAK_HOURS', _('Désengorgement Heures de Pointe')
        RECURRING = 'RECURRING', _('Covoiturage Régulier Domicile-Travail')

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='personalized_challenges',
        verbose_name=_('Utilisateur ciblé')
    )
    title = models.CharField(_('Titre du défi'), max_length=150)
    description = models.TextField(_('Consigne et explication'))
    category = models.CharField(_('Catégorie'), max_length=30, choices=CategoryChoices.choices, default=CategoryChoices.CO2)
    difficulty = models.CharField(_('Difficulté'), max_length=15, choices=DifficultyChoices.choices, default=DifficultyChoices.EASY)
    
    target_value = models.FloatField(_('Objectif à atteindre'))
    current_value = models.FloatField(_('Progression actuelle'), default=0.0)
    unit = models.CharField(_('Unité'), max_length=20, default='kg CO₂')
    
    points_reward = models.PositiveIntegerField(_('Récompense en points'), default=150)
    badge_reward = models.ForeignKey(Badge, on_delete=models.SET_NULL, null=True, blank=True, related_name='challenge_rewards')
    
    kmeans_cluster_tag = models.CharField(_('Tag cluster IA'), max_length=60, blank=True)
    status = models.CharField(_('Statut'), max_length=20, choices=StatusChoices.choices, default=StatusChoices.ACTIVE)
    
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Défi Personnalisé IA')
        verbose_name_plural = _('Défis Personnalisés IA')
        ordering = ['status', 'end_date']

    def __str__(self):
        return f"{self.user.username} - [{self.get_difficulty_display()}] {self.title} ({self.progress_percentage}%)"

    @property
    def progress_percentage(self) -> int:
        if self.target_value <= 0:
            return 100
        val = int((self.current_value / self.target_value) * 100)
        return min(100, max(0, val))

    @property
    def is_finished(self) -> bool:
        return self.current_value >= self.target_value


class CollectiveChallenge(models.Model):
    """
    Défis collectifs d'équipes, universités, entreprises ou quartiers du Grand Tunis,
    avec jauge communautaire visible en temps réel.
    """
    class ScopeChoices(models.TextChoices):
        GLOBAL = 'GLOBAL', _('Grand Tunis (Tous les citoyens)')
        UNIVERSITY = 'UNIVERSITY', _('Inter-Universités (ESPRIT, INSAT, etc.)')
        COMPANY = 'COMPANY', _('Inter-Entreprises (Lac 2, Charguia)')
        DISTRICT = 'DISTRICT', _('Inter-Quartiers (Ariana, Marsa, Bardo)')

    title = models.CharField(_('Nom du défi collectif'), max_length=160)
    description = models.TextField(_('Objectif d\'impact communautaire'))
    scope = models.CharField(_('Périmètre'), max_length=30, choices=ScopeChoices.choices, default=ScopeChoices.GLOBAL)
    target_entity_name = models.CharField(
        _('Entité ou groupe ciblé'),
        max_length=120,
        default='Grand Tunis',
        help_text=_('Ex: Campus ESPRIT & INSAT, Pôle Entreprises Lac 2, Commune de La Marsa')
    )
    target_co2_kg = models.FloatField(_('Objectif collectif CO₂ (kg)'), default=5000.0)
    current_co2_kg = models.FloatField(_('CO₂ économisé à ce jour (kg)'), default=0.0)
    
    reward_description = models.CharField(
        _('Récompense communautaire finale'),
        max_length=255,
        default='Plantation d\'arbres + 20% de remise chez tous nos commerçants partenaires'
    )
    icon = models.CharField(_('Icône'), max_length=50, default='bi-globe-americas')
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    is_active = models.BooleanField(_('Défi en cours'), default=True)
    
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='joined_collective_challenges',
        blank=True
    )

    class Meta:
        verbose_name = _('Défi Collectif Communautaire')
        verbose_name_plural = _('Défis Collectifs Communautaires')
        ordering = ['-is_active', 'end_date']

    def __str__(self):
        return f"{self.title} ({self.progress_percentage}% - {self.target_entity_name})"

    @property
    def progress_percentage(self) -> int:
        if self.target_co2_kg <= 0:
            return 100
        val = int((self.current_co2_kg / self.target_co2_kg) * 100)
        return min(100, max(0, val))

    @property
    def participants_count(self) -> int:
        return self.participants.count()


class RewardPartner(models.Model):
    """
    Commerçant ou partenaire éco-responsable du Grand Tunis offrant des récompenses.
    """
    class CategoryChoices(models.TextChoices):
        COFFEE_FOOD = 'COFFEE_FOOD', _('Cafés & Restauration Éthique')
        MOBILITY = 'MOBILITY', _('Mobilité & Recharges Électriques')
        LEISURE = 'LEISURE', _('Sport, Bien-être & Loisirs')
        ECO_SHOP = 'ECO_SHOP', _('Boutiques Zéro Déchet & Bio')

    name = models.CharField(_('Nom du partenaire'), max_length=120)
    slug = models.SlugField(_('Identifiant slug'), unique=True)
    category = models.CharField(_('Catégorie'), max_length=30, choices=CategoryChoices.choices, default=CategoryChoices.COFFEE_FOOD)
    icon = models.CharField(_('Icône'), max_length=50, default='bi-cup-hot-fill')
    description = models.TextField(_('Présentation du commerce'))
    location_name = models.CharField(_('Adresse à Tunis'), max_length=150, default='Les Berges du Lac 2, Tunis')
    latitude = models.FloatField(_('Latitude'), default=36.8392)
    longitude = models.FloatField(_('Longitude'), default=10.2447)
    validation_pin = models.CharField(_('Code PIN Commerçant de secours'), max_length=6, default='2026')
    is_verified = models.BooleanField(_('Partenaire vérifié'), default=True)

    class Meta:
        verbose_name = _('Partenaire Récompenses')
        verbose_name_plural = _('Partenaires Récompenses')

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class RewardItem(models.Model):
    """
    Offre / coupon disponible dans la boutique éco-rewards.
    """
    partner = models.ForeignKey(RewardPartner, on_delete=models.CASCADE, related_name='rewards')
    title = models.CharField(_('Intitulé de l\'avantage'), max_length=120)
    description = models.TextField(_('Conditions d\'utilisation'))
    points_cost = models.PositiveIntegerField(_('Coût en éco-points'), default=200)
    discount_label = models.CharField(
        _('Étiquette réduction'),
        max_length=60,
        help_text=_('Ex: 1 Café Offert, -25% sur l\'addition, 30 min de Recharge Gratuite')
    )
    stock = models.PositiveIntegerField(_('Nombre de coupons disponibles'), default=50)
    is_active = models.BooleanField(_('Offre active'), default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('Article Récompense')
        verbose_name_plural = _('Articles Récompenses')
        ordering = ['points_cost']

    def __str__(self):
        return f"{self.partner.name} : {self.title} ({self.points_cost} pts)"


class UserCoupon(models.Model):
    """
    Coupon généré avec code unique et QR Code scannable/validable en caisse.
    """
    class StatusChoices(models.TextChoices):
        VALID = 'VALID', _('Valide (Non utilisé)')
        USED = 'USED', _('Validé / Utilisé')
        EXPIRED = 'EXPIRED', _('Expiré')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='coupons')
    reward = models.ForeignKey(RewardItem, on_delete=models.CASCADE, related_name='claimed_coupons')
    coupon_code = models.CharField(_('Code Coupon Unique'), max_length=32, unique=True, db_index=True, blank=True, help_text=_('Généré automatiquement si laissé vide.'))
    qr_code_image = models.TextField(_('QR Code Base64 Data URI'), blank=True, editable=False)
    status = models.CharField(_('Statut'), max_length=20, choices=StatusChoices.choices, default=StatusChoices.VALID)
    
    claimed_at = models.DateTimeField(_('Date d\'obtention'), auto_now_add=True)
    used_at = models.DateTimeField(_('Date de validation en boutique'), null=True, blank=True)
    validated_by_pin = models.BooleanField(_('Validé via PIN commerçant'), default=False)

    class Meta:
        verbose_name = _('Coupon Utilisateur')
        verbose_name_plural = _('Coupons Utilisateurs')
        ordering = ['-claimed_at']

    def __str__(self):
        return f"{self.coupon_code} - {self.reward.title} ({self.user.username}) [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        if not self.coupon_code:
            from .services.qr_service import generate_unique_coupon_code
            self.coupon_code = generate_unique_coupon_code()
        if not self.qr_code_image and self.reward_id and self.user_id:
            from .services.qr_service import generate_coupon_qr_base64
            self.qr_code_image = generate_coupon_qr_base64(
                coupon_code=self.coupon_code,
                reward_title=self.reward.title,
                user_identifier=self.user.username,
            )
        super().save(*args, **kwargs)

    def mark_as_used(self):
        self.status = self.StatusChoices.USED
        self.used_at = timezone.now()
        self.save()
