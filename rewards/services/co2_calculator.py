"""
Service de calcul physique de CO2 économisé et d'attribution d'EcoPoints.
Respecte les facteurs d'émission réels du parc automobile tunisien et valorise :
- L'impact carbone réel plutôt que le simple nombre de trajets
- Le taux d'occupation du véhicule (mutualisation)
- Les bonus pour les heures de pointe (désengorgement) et météo défavorable
- La traçabilité comptable dans EcoTransaction
- La mise à jour de la progression des défis et badges
"""
import math
import logging
from datetime import datetime, time
from typing import Dict, Any, Optional, Tuple

from django.db import transaction
from django.utils import timezone
from django.conf import settings
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Facteurs d'émissions (kg CO2 / km) pour le contexte du Grand Tunis
EMISSION_FACTORS = {
    'SOLO_THERMAL_BASELINE': 0.145,   # Véhicule thermique solo de référence (145g CO2/km)
    'ELECTRIC': 0.015,                # Véhicule électrique (émissions indirectes réseau)
    'HYBRID': 0.075,                  # Véhicule hybride
    'THERMAL_ECO': 0.110,             # Véhicule thermique éco-efficient
    'BICYCLE_SCOOTER': 0.000,         # Mobilité douce (zéro émission directe)
    'NONE': 0.145,                    # Hypothèse thermique par défaut
}

# Taux de conversion : 100 EcoPoints par 1 kg de CO2 réellement évité
POINTS_PER_KG_CO2 = 100


def is_peak_hour(dt: Optional[datetime] = None) -> bool:
    """Détecte si l'horaire correspond aux heures de pointe du Grand Tunis."""
    if dt is None:
        dt = timezone.now()
    t = dt.time()
    morning_peak = time(7, 15) <= t <= time(9, 30)
    evening_peak = time(16, 30) <= t <= time(19, 0)
    return morning_peak or evening_peak


def compute_ride_carbon_savings(
    distance_km: float,
    vehicle_type: str = 'THERMAL_ECO',
    occupants_count: int = 2,
    departure_dt: Optional[datetime] = None,
    weather_condition: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calcule scientifiquement l'économie de CO2 et les points gagnés.
    
    Formule :
      CO2_évité_total = (Facteur_Solo_Référence * Occupants_Covoiturés) - (Facteur_Véhicule_Utilisé * Distance)
      Pour chaque passager : Évite 1 trajet solo complet
      Pour le conducteur : Évite l'émission des véhicules des passagers qui seraient partis seuls
    """
    distance_km = max(0.5, float(distance_km))
    occupants_count = max(1, int(occupants_count))
    vehicle_factor = EMISSION_FACTORS.get(vehicle_type, EMISSION_FACTORS['THERMAL_ECO'])
    solo_baseline = EMISSION_FACTORS['SOLO_THERMAL_BASELINE']

    # Nombre de voitures retirées de la route = nombre de passagers covoiturés
    passengers_count = max(1, occupants_count - 1)
    
    # Émissions totales si chacun conduisait seul sa propre voiture thermique
    emissions_if_all_solo = occupants_count * (solo_baseline * distance_km)
    
    # Émission réelle du véhicule partagé
    actual_vehicle_emission = vehicle_factor * distance_km
    
    # Total de CO2 épargné par le trajet collectif
    total_co2_saved_kg = max(0.1, round(emissions_if_all_solo - actual_vehicle_emission, 2))
    
    # Part par passager et part conducteur
    co2_saved_per_passenger = round(total_co2_saved_kg / max(1, occupants_count), 2)
    
    # Calcul des points de base
    base_points = int(round(total_co2_saved_kg * POINTS_PER_KG_CO2))

    # Bonus Heure de Pointe (+25% de points pour désengorger Tunis)
    peak_bonus_pts = 0
    if is_peak_hour(departure_dt):
        peak_bonus_pts = int(round(base_points * 0.25))

    # Bonus Météo / Pluie (+15% pour solidarité par mauvais temps)
    weather_bonus_pts = 0
    if weather_condition and any(w in weather_condition.lower() for w in ['pluie', 'rain', 'storm', 'orage']):
        weather_bonus_pts = int(round(base_points * 0.15))

    total_points = max(10, base_points + peak_bonus_pts + weather_bonus_pts)

    return {
        'distance_km': distance_km,
        'total_co2_saved_kg': total_co2_saved_kg,
        'co2_saved_per_person_kg': co2_saved_per_passenger,
        'base_points': base_points,
        'peak_bonus_pts': peak_bonus_pts,
        'weather_bonus_pts': weather_bonus_pts,
        'total_points': total_points,
        'trees_saved_ratio': round(total_co2_saved_kg / 21.77, 3),
        'is_peak': is_peak_hour(departure_dt),
    }


def get_or_create_gamification_profile(user):
    """Garantit l'existence du profil de gamification pour un utilisateur."""
    from ..models import UserGamificationProfile
    profile, created = UserGamificationProfile.objects.get_or_create(
        user=user,
        defaults={
            'district': 'Les Berges du Lac 2',
            'organization': 'ESPRIT',
        }
    )
    return profile


def award_ride_eco_points(ride, triggering_user=None, weather_condition: Optional[str] = None) -> Dict[str, Any]:
    """
    Attribue les EcoPoints et enregistre le CO2 économisé suite à la finalisation
    ou confirmation d'un trajet (interconnexion avec le module Match de Roua).
    """
    from ..models import EcoTransaction, PersonalizedChallenge, CollectiveChallenge, UserGamificationProfile
    
    # 1. Nombre d'occupants = 1 (conducteur) + nombre de réservations acceptées
    accepted_bookings = ride.bookings.filter(status='ACCEPTED').select_related('passenger')
    occupants_count = 1 + accepted_bookings.count()
    if occupants_count == 1 and ride.seats_available:
        occupants_count = 2  # Démo ou estimation par défaut

    vehicle_type = getattr(ride.user, 'vehicle_type', 'THERMAL_ECO')
    carbon_data = compute_ride_carbon_savings(
        distance_km=ride.distance_km,
        vehicle_type=vehicle_type,
        occupants_count=occupants_count,
        departure_dt=ride.departure_datetime,
        weather_condition=weather_condition,
    )

    awarded_results = []

    with transaction.atomic():
        # 2. Créditer le conducteur
        driver = ride.user
        driver_profile = get_or_create_gamification_profile(driver)
        driver_pts = carbon_data['total_points']
        driver_co2 = carbon_data['total_co2_saved_kg']

        driver.eco_points += driver_pts
        driver.save(update_fields=['eco_points'])

        driver_profile.total_co2_saved_kg = round(driver_profile.total_co2_saved_kg + driver_co2, 2)
        driver_profile.monthly_co2_saved_kg = round(driver_profile.monthly_co2_saved_kg + driver_co2, 2)
        driver_profile.last_activity_date = timezone.now().date()
        driver_profile.save(update_fields=['total_co2_saved_kg', 'monthly_co2_saved_kg', 'last_activity_date'])

        # Transaction conducteur
        EcoTransaction.objects.create(
            user=driver,
            points=driver_pts,
            co2_saved_kg=driver_co2,
            transaction_type=EcoTransaction.TransactionTypeChoices.RIDE_DRIVER,
            ride=ride,
            description=f"Covoiturage {ride.origin_address[:20]} ➔ {ride.destination_address[:20]} ({carbon_data['distance_km']} km)"
        )
        awarded_results.append({
            'user': driver.username,
            'role': 'CONDUCTEUR',
            'points': driver_pts,
            'co2_saved_kg': driver_co2,
        })

        # Mettre à jour les défis du conducteur
        update_user_challenges_progress(driver, co2_added=driver_co2, rides_added=1, is_peak=carbon_data['is_peak'])
        check_and_award_badges(driver)

        # 3. Créditer chaque passager confirmé
        for booking in accepted_bookings:
            passenger = booking.passenger
            pass_profile = get_or_create_gamification_profile(passenger)
            pass_pts = max(15, int(carbon_data['total_points'] / occupants_count))
            pass_co2 = carbon_data['co2_saved_per_person_kg']

            passenger.eco_points += pass_pts
            passenger.save(update_fields=['eco_points'])

            pass_profile.total_co2_saved_kg = round(pass_profile.total_co2_saved_kg + pass_co2, 2)
            pass_profile.monthly_co2_saved_kg = round(pass_profile.monthly_co2_saved_kg + pass_co2, 2)
            pass_profile.last_activity_date = timezone.now().date()
            pass_profile.save(update_fields=['total_co2_saved_kg', 'monthly_co2_saved_kg', 'last_activity_date'])

            EcoTransaction.objects.create(
                user=passenger,
                points=pass_pts,
                co2_saved_kg=pass_co2,
                transaction_type=EcoTransaction.TransactionTypeChoices.RIDE_PASSENGER,
                ride=ride,
                description=f"Passager covoiturage vert avec {driver.get_full_name() or driver.username}"
            )
            awarded_results.append({
                'user': passenger.username,
                'role': 'PASSAGER',
                'points': pass_pts,
                'co2_saved_kg': pass_co2,
            })

            update_user_challenges_progress(passenger, co2_added=pass_co2, rides_added=1, is_peak=carbon_data['is_peak'])
            check_and_award_badges(passenger)

        # 4. Mettre à jour les jauges des défis collectifs actifs
        active_collective = CollectiveChallenge.objects.filter(is_active=True)
        for col_challenge in active_collective:
            col_challenge.current_co2_kg = round(col_challenge.current_co2_kg + carbon_data['total_co2_saved_kg'], 2)
            col_challenge.save(update_fields=['current_co2_kg'])

    # 5. Broadcast en temps réel sur WebSocket pour mettre à jour les classements en direct
    broadcast_leaderboard_update()

    return {
        'carbon_data': carbon_data,
        'awarded_results': awarded_results,
    }


def update_user_challenges_progress(user, co2_added: float = 0.0, rides_added: int = 0, is_peak: bool = False):
    """Incrémente la progression des défis personnalisés en cours de l'utilisateur."""
    from ..models import PersonalizedChallenge
    active_challenges = PersonalizedChallenge.objects.filter(user=user, status='ACTIVE')
    for ch in active_challenges:
        if ch.category == 'CO2' and co2_added > 0:
            ch.current_value = round(ch.current_value + co2_added, 2)
        elif ch.category == 'RIDES' and rides_added > 0:
            ch.current_value = round(ch.current_value + rides_added, 1)
        elif ch.category == 'PEAK_HOURS' and is_peak:
            ch.current_value = round(ch.current_value + 1, 1)

        if ch.is_finished:
            ch.status = 'COMPLETED'
        ch.save(update_fields=['current_value', 'status'])


def sync_user_challenges_with_activity(user):
    """
    Synchronise automatiquement la progression des défis d'un utilisateur
    avec ses vrais trajets et réservations enregistrés dans MobilityMatch.
    """
    from ..models import PersonalizedChallenge
    from match.models import Ride, RideBooking

    # 1. Trajets en tant que conducteur
    driver_rides = Ride.objects.filter(user=user).count()

    # 2. Réservations en tant que passager (en attente ou acceptées)
    passenger_bookings = RideBooking.objects.filter(
        passenger=user,
        status__in=[RideBooking.StatusChoices.PENDING, RideBooking.StatusChoices.ACCEPTED]
    ).count()

    total_rides = driver_rides + passenger_bookings

    # 3. Économie de CO2 cumulée
    profile = getattr(user, 'gamification_profile', None)
    total_co2 = profile.total_co2_saved_kg if profile else 0.0

    # 4. Trajets aux heures de pointe
    peak_count = 0
    for r in Ride.objects.filter(user=user):
        if r.departure_datetime and ((7 <= r.departure_datetime.hour <= 9) or (16 <= r.departure_datetime.hour <= 19)):
            peak_count += 1
    for b in RideBooking.objects.filter(passenger=user, status__in=['PENDING', 'ACCEPTED']).select_related('ride'):
        if b.ride.departure_datetime and ((7 <= b.ride.departure_datetime.hour <= 9) or (16 <= b.ride.departure_datetime.hour <= 19)):
            peak_count += 1

    active_challenges = PersonalizedChallenge.objects.filter(
        user=user, status__in=['ACTIVE', 'COMPLETED']
    )

    for ch in active_challenges:
        modified = False
        if ch.category in ['RIDES', 'RECURRING'] and total_rides > 0:
            new_val = min(ch.target_value, float(total_rides))
            if new_val > ch.current_value:
                ch.current_value = new_val
                modified = True
        elif ch.category == 'CO2' and total_co2 > 0:
            new_val = min(ch.target_value, round(float(total_co2), 1))
            if new_val > ch.current_value:
                ch.current_value = new_val
                modified = True
        elif ch.category == 'PEAK_HOURS' and peak_count > 0:
            new_val = min(ch.target_value, float(peak_count))
            if new_val > ch.current_value:
                ch.current_value = new_val
                modified = True

        if ch.is_finished and ch.status == 'ACTIVE':
            ch.status = 'COMPLETED'
            modified = True

        if modified:
            ch.save(update_fields=['current_value', 'status'])



def check_and_award_badges(user):
    """Vérifie si les critères d'un badge sont atteints et l'attribue automatiquement."""
    from ..models import Badge, UserBadge, EcoTransaction
    profile = get_or_create_gamification_profile(user)
    existing_badge_ids = set(user.earned_badges.values_list('badge_id', flat=True))

    all_badges = Badge.objects.exclude(id__in=existing_badge_ids)
    for b in all_badges:
        unlocked = False
        if b.threshold_type == 'CO2_KG' and profile.total_co2_saved_kg >= b.threshold_value:
            unlocked = True
        elif b.threshold_type == 'POINTS' and user.eco_points >= b.threshold_value:
            unlocked = True
        elif b.threshold_type == 'RIDES_COUNT':
            rides_count = EcoTransaction.objects.filter(
                user=user,
                transaction_type__in=['RIDE_DRIVER', 'RIDE_PASSENGER']
            ).count()
            if rides_count >= b.threshold_value:
                unlocked = True
        elif b.threshold_type == 'STREAK_DAYS' and profile.streak_days >= b.threshold_value:
            unlocked = True

        if unlocked:
            UserBadge.objects.create(user=user, badge=b)
            # Bonus de points pour l'obtention du badge
            if b.points_reward > 0:
                user.eco_points += b.points_reward
                user.save(update_fields=['eco_points'])
                EcoTransaction.objects.create(
                    user=user,
                    points=b.points_reward,
                    co2_saved_kg=0.0,
                    transaction_type=EcoTransaction.TransactionTypeChoices.BADGE_UNLOCK,
                    description=f"Badge débloqué : {b.name}"
                )


def broadcast_leaderboard_update():
    """Émet une notification WebSocket aux clients connectés au classement."""
    try:
        channel_layer = get_channel_layer()
        if channel_layer:
            async_to_sync(channel_layer.group_send)(
                'rewards_leaderboard',
                {
                    'type': 'leaderboard_updated',
                    'message': 'Nouveau score enregistré ! Classement actualisé.'
                }
            )
    except Exception as e:
        logger.debug("Leaderboard WebSocket broadcast skipped: %s", e)
