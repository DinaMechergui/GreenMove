"""
Moteur d'intelligence artificielle de mise en correspondance (MobilityMatch AI).
Score de compatibilité multi-critères 0-100% pondérant :

    1. Chevauchement du tracé (Fréchet/Hausdorff + % de recouvrement)  30%
    2. Proximité spatiale des extrémités (départ / arrivée)            15%
    3. Écart horaire de départ                                         20%
    4. Détour imposé au conducteur                                     10%
    5. Préférences (mixte / femmes uniquement / non-fumeur)            10%
    6. Score de fiabilité (avis post-trajet)                           10%
    7. Bonus véhicule vert                                             5%
"""
from typing import List, Dict, Any, Optional
from datetime import datetime

from .routing import calculate_haversine_distance
from .similarity import trajectory_similarity

# Pondérations du modèle (somme = 1.0)
WEIGHTS = {
    'overlap': 0.30,
    'spatial': 0.15,
    'temporal': 0.20,
    'detour': 0.10,
    'preferences': 0.10,
    'reliability': 0.10,
    'eco': 0.05,
}

TOLERANCE_TIME_MIN = 90.0   # écart horaire toléré
DETOUR_FULL_KM = 12.0       # détour total au-delà duquel le score spatial tombe à 0
UNKNOWN_TIME_SCORE = 0.5    # score temporel neutre quand aucun horaire de recherche
MIN_REAL_OVERLAP_PCT = 10.0 # sous ce seuil, deux vrais tracés ne chevauchent pas
ROUTE_CONFIDENCE = 0.8      # pénalité quand un tracé n'est pas réel (ligne droite)


def _eco_score(driver) -> tuple:
    """(score 0-1, badge) du véhicule du conducteur."""
    vehicle_type = getattr(driver, 'vehicle_type', 'NONE')
    mapping = {
        'ELECTRIC': (1.0, "Zéro Émission (100% Électrique)"),
        'BICYCLE_SCOOTER': (0.95, "Mobilité douce (Vélo / Trottinette)"),
        'HYBRID': (0.85, "Hybride Éco"),
        'THERMAL_ECO': (0.65, "Thermique Économe"),
    }
    return mapping.get(vehicle_type, (0.45, "Standard"))


def _preferences_score(query_user, driver) -> tuple:
    """
    Compatibilité des préférences de covoiturage.
    Retourne (score 0-1, raison).
    """
    if query_user is None or not getattr(query_user, 'is_authenticated', False):
        return 1.0, ""

    driver_pref = getattr(driver, 'ride_preference', 'MIXTE')
    query_pref = getattr(query_user, 'ride_preference', 'MIXTE')
    driver_gender = getattr(driver, 'gender', '')
    query_gender = getattr(query_user, 'gender', '')

    # Règle « femmes uniquement »
    if driver_pref == 'WOMEN_ONLY' and query_gender != 'F':
        return 0.0, "Trajet réservé aux femmes"
    if query_pref == 'WOMEN_ONLY' and driver_gender != 'F':
        return 0.0, "Préférence femmes uniquement non respectée"

    # Règle tabac : un non-fumeur ne partage pas avec un fumeur (incompatibilité dure)
    driver_smoker = bool(getattr(driver, 'is_smoker', False))
    query_smoker = bool(getattr(query_user, 'is_smoker', False))
    if driver_smoker != query_smoker:
        return 0.0, "Préférence non-fumeur incompatible"

    return 1.0, ""


def compute_ride_match_score(
    query_origin: tuple,
    query_dest: tuple,
    query_time: Optional[datetime],
    candidate_ride,
    query_user=None,
    query_polyline: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Calcule le score de compatibilité multi-critères (0-100%) entre une recherche
    et un trajet candidat, avec détail du breakdown.
    """
    origin_lat, origin_lon = query_origin
    dest_lat, dest_lon = query_dest

    # Les deux tracés sont-ils réels (polylignes routières) ou du repli "ligne droite" ?
    query_has_route = bool(query_polyline and len(query_polyline) >= 2)
    candidate_has_route = len(candidate_ride.polyline_coords) >= 2

    # --- 1. Chevauchement du tracé (Fréchet / Hausdorff / % de recouvrement) ---
    query_line = query_polyline if query_has_route else [
        (origin_lat, origin_lon), (dest_lat, dest_lon)
    ]
    candidate_line = candidate_ride.polyline_coords
    if len(candidate_line) < 2:
        candidate_line = [
            (candidate_ride.origin_lat, candidate_ride.origin_lon),
            (candidate_ride.destination_lat, candidate_ride.destination_lon),
        ]
    similarity = trajectory_similarity(query_line, candidate_line)
    overlap_score = similarity['similarity_pct'] / 100.0

    # --- 2. Proximité spatiale (extrémités) ---
    dist_origin = calculate_haversine_distance(
        origin_lat, origin_lon, candidate_ride.origin_lat, candidate_ride.origin_lon
    )
    dist_dest = calculate_haversine_distance(
        dest_lat, dest_lon, candidate_ride.destination_lat, candidate_ride.destination_lon
    )
    total_detour_km = dist_origin + dist_dest
    spatial_score = max(0.0, 1.0 - (total_detour_km / DETOUR_FULL_KM))

    # --- 3. Écart horaire ---
    time_score = UNKNOWN_TIME_SCORE
    time_diff_min = 0.0
    if query_time and candidate_ride.departure_datetime:
        q_naive = query_time.replace(tzinfo=None) if query_time.tzinfo else query_time
        r_naive = (
            candidate_ride.departure_datetime.replace(tzinfo=None)
            if candidate_ride.departure_datetime.tzinfo
            else candidate_ride.departure_datetime
        )
        time_diff_min = abs((q_naive - r_naive).total_seconds()) / 60.0
        time_score = max(0.0, 1.0 - (time_diff_min / TOLERANCE_TIME_MIN))

    # --- 4. Détour relatif au trajet du conducteur ---
    ride_distance = max(candidate_ride.distance_km, 0.1)
    detour_ratio = total_detour_km / ride_distance
    detour_score = max(0.0, 1.0 - (detour_ratio / 0.5))  # >50% de détour ⇒ 0

    # --- 5. Préférences (mixte / femmes uniquement / non-fumeur) ---
    driver = candidate_ride.user
    preferences_score, preference_reason = _preferences_score(query_user, driver)

    # --- 6. Fiabilité (moyenne des avis post-trajet) ---
    reliability_raw = float(getattr(driver, 'reliability_score', 5.0) or 5.0)
    reliability_score = max(0.0, min(1.0, reliability_raw / 5.0))

    # --- 7. Bonus écologique du véhicule ---
    eco_bonus, vehicle_badge = _eco_score(driver)

    # --- Modèle pondéré global ---
    breakdown = {
        'overlap': round(overlap_score * 100),
        'spatial': round(spatial_score * 100),
        'temporal': round(time_score * 100),
        'detour': round(detour_score * 100),
        'preferences': round(preferences_score * 100),
        'reliability': round(reliability_score * 100),
        'eco': round(eco_bonus * 100),
    }

    weighted_score = (
        overlap_score * WEIGHTS['overlap']
        + spatial_score * WEIGHTS['spatial']
        + time_score * WEIGHTS['temporal']
        + detour_score * WEIGHTS['detour']
        + preferences_score * WEIGHTS['preferences']
        + reliability_score * WEIGHTS['reliability']
        + eco_bonus * WEIGHTS['eco']
    )

    final_match_pct = round(weighted_score * 100)
    # Aucun plancher artificiel : un mauvais chevauchement de routes doit être visible.
    # Une pénalité s'applique quand l'un des tracés est un repli "ligne droite" (non réel).
    if not (query_has_route and candidate_has_route):
        final_match_pct = round(final_match_pct * ROUTE_CONFIDENCE)
    final_match_pct = max(1, min(99, final_match_pct))

    # --- Verdict IA (atouts du match) ---
    reasons = []
    if similarity['overlap_pct'] >= 60:
        reasons.append(f"Tracé partagé à {round(similarity['overlap_pct'])}%")
    elif similarity['overlap_pct'] < MIN_REAL_OVERLAP_PCT and query_has_route and candidate_has_route:
        reasons.append("Routes quasi disjointes")
    if not (query_has_route and candidate_has_route):
        reasons.append("Tracés approximatifs (routes non enregistrées)")
    if dist_origin <= 1.5:
        reasons.append(f"Prise en charge tout près ({round(dist_origin * 1000)} m)")
    if dist_dest <= 2.0:
        reasons.append(f"Dépose optimale ({round(dist_dest, 1)} km)")
    if time_diff_min <= 20 and query_time:
        reasons.append("Horaires parfaitement alignés")
    if vehicle_badge not in ("Standard",):
        reasons.append(vehicle_badge)
    if reliability_raw >= 4.5:
        reasons.append(f"Conducteur très fiable ({reliability_raw}/5)")
    if preferences_score == 0.0 and preference_reason:
        reasons.append(preference_reason)

    ai_verdict = " • ".join(reasons) if reasons else "Trajet compatible sur le même axe de circulation"

    return {
        "match_percentage": final_match_pct,
        "breakdown": breakdown,
        "similarity": similarity,
        "spatial_score": round(spatial_score * 100),
        "dist_origin_km": round(dist_origin, 1),
        "dist_dest_km": round(dist_dest, 1),
        "total_detour_km": round(total_detour_km, 1),
        "time_diff_min": round(time_diff_min),
        "vehicle_badge": vehicle_badge,
        "reliability_score": reliability_raw,
        "preference_ok": preferences_score > 0.0,
        "preference_reason": preference_reason,
        "route_query_real": query_has_route,
        "route_candidate_real": candidate_has_route,
        "route_confidence": 1.0 if (query_has_route and candidate_has_route) else ROUTE_CONFIDENCE,
        "ai_verdict": ai_verdict,
        "co2_saved_estimated": candidate_ride.estimated_co2_saved,
    }


def find_best_matches(
    origin_coords: tuple,
    dest_coords: tuple,
    target_time: Optional[datetime],
    rides_queryset,
    limit: int = 10,
    query_user=None,
    query_polyline: Optional[list] = None,
) -> List[Dict[str, Any]]:
    """
    Recherche et classe les trajets les plus pertinents avec le moteur IA.
    """
    results = []
    for ride in rides_queryset:
        analysis = compute_ride_match_score(
            origin_coords, dest_coords, target_time, ride,
            query_user=query_user,
            query_polyline=query_polyline,
        )
        # Deux vrais tracés routiers qui ne se chevauchent pas = mauvais match, on l'exclut.
        if (
            analysis["route_query_real"]
            and analysis["route_candidate_real"]
            and analysis["similarity"]["overlap_pct"] < MIN_REAL_OVERLAP_PCT
        ):
            continue
        results.append({
            "ride": ride,
            "analysis": analysis,
            "score": analysis["match_percentage"],
        })

    # Tri par score IA décroissant (les préférences incompatibles passent en dernier)
    results.sort(key=lambda x: (x["analysis"]["preference_ok"], x["score"]), reverse=True)
    return results[:limit]
