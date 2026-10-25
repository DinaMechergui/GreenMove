"""
Calculateur de partage des frais & CO₂ économisé par duo (MobilityMatch).
Modèle simple et explicite pour 1 conducteur + 1 passager (duo).
"""
from typing import Dict, Optional

from .routing import calculate_haversine_distance

# Coût d'exploitation moyen d'une voiture thermique (carburant + usure) en Tunisie
COST_PER_KM_TND = 0.85
# Émission de référence d'une voiture individuelle (kg CO₂ / km) — base GreenMove
CO2_FACTOR_KG_PER_KM = 0.13
# Prix moyen du carburant (DT/L) et consommation (L/100km) pour l'estimation
FUEL_PRICE_TND_PER_L = 1.80
CONSUMPTION_L_PER_100KM = 6.5


def estimate_trip_cost(distance_km: float) -> float:
    """Coût total estimé du trajet (DT) basé sur kilométrage × coût au km."""
    return round(distance_km * COST_PER_KM_TND, 2)


def ride_effective_distance_km(ride) -> float:
    """
    Distance d'un trajet : longueur du tracé routier (polyline) si disponible,
    sinon distance Haversine (ligne droite) entre départ et arrivée.
    """
    distance_km = ride.distance_km
    coords = ride.polyline_coords
    if len(coords) >= 2:
        total = 0.0
        for i in range(1, len(coords)):
            total += calculate_haversine_distance(
                coords[i - 1][0], coords[i - 1][1],
                coords[i][0], coords[i][1],
            )
        if total > 0:
            distance_km = round(total, 1)
    return round(float(distance_km or 0.0), 1)


def compute_duo_split(ride, distance_km: Optional[float] = None,
                      passenger_price: Optional[float] = None) -> Dict:
    """
    Détail du partage des frais et du CO₂ pour un duo
    (le conducteur + 1 passager sur ce trajet).

    Args:
        ride: instance de Ride
        distance_km: surcharge de distance (sinon distance routière si dispo, sinon Haversine)
        passenger_price: prix convenu par passager (sinon ride.price_tnd, sinon part équitable)

    Returns:
        {
          "distance_km", "trip_cost_tnd",
          "passenger_pays_tnd", "driver_net_cost_tnd", "driver_saves_tnd",
          "cost_per_km_tnd",
          "co2_duo_saved_kg",     # CO₂ évité par le duo (voiture retirée de la route)
          "co2_per_person_kg",    # réparti par personne
          "co2_solo_vs_duo_kg",   # émission par personne : solo vs duo
          "fuel_liter_saved",
        }
    """
    # 1. Distance réelle (tracé routier si dispo, sinon Haversine)
    if distance_km is None:
        distance_km = ride_effective_distance_km(ride)
    distance_km = round(float(distance_km or 0.0), 1)

    # 2. Coûts
    trip_cost = estimate_trip_cost(distance_km)
    if passenger_price is None:
        passenger_price = float(ride.price_tnd) if ride.price_tnd else 0.0
    if passenger_price > 0:
        passenger_pays = round(min(passenger_price, trip_cost), 2)
    else:
        # Pas de prix fixé : part équitable 50/50
        passenger_pays = round(trip_cost / 2.0, 2)
    driver_net = round(max(0.0, trip_cost - passenger_pays), 2)
    driver_saves = passenger_pays  # ce que le conducteur ne sort pas de sa poche

    # 3. CO₂ : le duo retire une voiture de la route
    co2_duo = round(distance_km * CO2_FACTOR_KG_PER_KM, 2)
    co2_per_person = round(co2_duo / 2.0, 2)
    liters = round(distance_km * CONSUMPTION_L_PER_100KM / 100.0, 2)

    return {
        "distance_km": distance_km,
        "trip_cost_tnd": trip_cost,
        "passenger_pays_tnd": passenger_pays,
        "driver_net_cost_tnd": driver_net,
        "driver_saves_tnd": driver_saves,
        "cost_per_km_tnd": COST_PER_KM_TND,
        "co2_duo_saved_kg": co2_duo,
        "co2_per_person_kg": co2_per_person,
        "co2_total_kg": co2_duo,
        "co2_solo_vs_duo_kg": {
            "solo": co2_duo,
            "duo": co2_per_person,
        },
        "fuel_liter_saved": liters,
        "fuel_price_tnd": FUEL_PRICE_TND_PER_L,
    }


def compute_custom_split(distance_km: float, passengers: int = 2,
                         total_cost: Optional[float] = None) -> Dict:
    """
    Calculateur libre (page outils) : partage au choix entre N personnes.
    """
    distance_km = round(float(distance_km or 0.0), 1)
    passengers = max(1, int(passengers))
    trip_cost = round(total_cost, 2) if total_cost is not None else estimate_trip_cost(distance_km)
    per_person = round(trip_cost / passengers, 2)
    co2_total = round(distance_km * CO2_FACTOR_KG_PER_KM, 2)
    return {
        "distance_km": distance_km,
        "passengers": passengers,
        "trip_cost_tnd": trip_cost,
        "per_person_tnd": per_person,
        "co2_total_kg": co2_total,
        "co2_duo_saved_kg": co2_total,
        "co2_per_person_kg": round(co2_total / passengers, 2),
        "cost_per_km_tnd": COST_PER_KM_TND,
        "fuel_liter_saved": round(distance_km * CONSUMPTION_L_PER_100KM / 100.0, 2),
        "fuel_price_tnd": FUEL_PRICE_TND_PER_L,
    }
