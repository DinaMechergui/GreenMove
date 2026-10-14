"""
Service de calcul d'itinéraires et d'empreinte carbone pour MobilityMatch.
Utilise en priorité OpenRouteService, puis OSRM public en secours,
et enfin un calcul géodésique interne si aucune API externe n'est joignable.
"""
import math
import logging
from typing import Dict, Any, List
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcule la distance géodésique en kilomètres."""
    r = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (math.sin(d_lat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round(r * c, 2)


def get_route_details(lat1: float, lon1: float, lat2: float, lon2: float) -> Dict[str, Any]:
    """
    Récupère le tracé routier, la distance exacte et la durée estimée.
    Ne lève jamais d'exception et garantit toujours une réponse exploitable par Leaflet.
    """
    cache_key = f"route_{lat1:.4f}_{lon1:.4f}_{lat2:.4f}_{lon2:.4f}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    ors_key = getattr(settings, 'ORS_API_KEY', '')

    # 1. Tentative avec OpenRouteService si une clé est configurée
    if ors_key:
        try:
            headers = {
                'Authorization': ors_key,
                'Content-Type': 'application/json'
            }
            body = {
                "coordinates": [[lon1, lat1], [lon2, lat2]]
            }
            res = requests.post(
                'https://api.openrouteservice.org/v2/directions/driving-car/geojson',
                headers=headers,
                json=body,
                timeout=3.5
            )
            if res.status_code == 200:
                data = res.json()
                features = data.get('features', [])
                if features:
                    props = features[0]['properties']['summary']
                    geometry = features[0]['geometry']['coordinates']
                    dist_km = round(props['distance'] / 1000.0, 1)
                    duration_min = round(props['duration'] / 60.0)
                    # ORS renvoie [lon, lat], on convertit en [lat, lon] pour Leaflet
                    leaflet_coords = [[coord[1], coord[0]] for coord in geometry]

                    result = {
                        "distance_km": dist_km,
                        "duration_min": duration_min,
                        "coordinates": leaflet_coords,
                        "source": "OpenRouteService",
                        "co2_saved_kg": round(dist_km * 0.13, 2),
                    }
                    cache.set(cache_key, result, 86400)
                    return result
        except Exception as exc:
            logger.warning(f"Échec OpenRouteService: {exc}. Bascule vers OSRM.")

    # 2. Secours avec le service OSRM public
    try:
        osrm_url = f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
        res = requests.get(osrm_url, timeout=3.5)
        if res.status_code == 200:
            data = res.json()
            routes = data.get('routes', [])
            if routes:
                route = routes[0]
                dist_km = round(route['distance'] / 1000.0, 1)
                duration_min = round(route['duration'] / 60.0)
                geometry = route['geometry']['coordinates']
                leaflet_coords = [[coord[1], coord[0]] for coord in geometry]

                result = {
                    "distance_km": dist_km,
                    "duration_min": duration_min,
                    "coordinates": leaflet_coords,
                    "source": "OSRM Public",
                    "co2_saved_kg": round(dist_km * 0.13, 2),
                }
                cache.set(cache_key, result, 86400)
                return result
    except Exception as exc:
        logger.warning(f"Échec OSRM: {exc}. Utilisation de l'interpolation géodésique interne.")

    # 3. Secours autonome interne (mode hors-ligne ou si les serveurs distants sont saturés)
    direct_dist = calculate_haversine_distance(lat1, lon1, lat2, lon2)
    # Distance routière estimée (~ 1.25x distance à vol d'oiseau à Tunis)
    road_dist = round(direct_dist * 1.25, 1)
    duration_min = max(int(road_dist * 2.2), 5)

    # Génération d'une polyligne interpolée réaliste
    steps = 8
    poly: List[List[float]] = []
    for i in range(steps + 1):
        ratio = i / float(steps)
        # Légère inflexion pour simuler un tracé routier
        curve = math.sin(ratio * math.pi) * 0.005
        p_lat = round(lat1 + (lat2 - lat1) * ratio + curve, 5)
        p_lon = round(lon1 + (lon2 - lon1) * ratio - curve, 5)
        poly.append([p_lat, p_lon])

    result = {
        "distance_km": road_dist,
        "duration_min": duration_min,
        "coordinates": poly,
        "source": "Moteur Interne Haversine",
        "co2_saved_kg": round(road_dist * 0.13, 2),
    }
    cache.set(cache_key, result, 3600)
    return result
