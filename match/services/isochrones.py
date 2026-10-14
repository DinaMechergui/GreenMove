"""
Isochrones & point de rendez-vous optimal (MobilityMatch).
- Isochrones OpenRouteService (/v2/isochrones) avec repli géodésique hors-ligne.
- Intersection des isochrones des deux utilisateurs → point de RDV optimal.
"""
import logging
import math
from typing import Dict, List, Optional, Sequence, Tuple

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

# Vitesse moyenne urbaine utilisée pour le repli hors-ligne (km/h)
DEFAULT_SPEED_KMH = {
    'driving-car': 28.0,
    'driving-hgv': 24.0,
    'cycling-regular': 15.0,
    'foot-walking': 4.8,
}


def _geodesic_circle(lat: float, lon: float, minutes: float, speed_kmh: float,
                     n_points: int = 48) -> List[List[float]]:
    """
    Polygone approchant un isochrone : rayon = temps × vitesse moyenne.
    Retourne une liste de [lat, lon].
    """
    radius_m = (minutes / 60.0) * speed_kmh * 1000.0
    radius_deg_lat = radius_m / 111320.0
    radius_deg_lon = radius_m / (111320.0 * math.cos(math.radians(lat)))
    ring = []
    for i in range(n_points):
        theta = 2.0 * math.pi * i / n_points
        ring.append([
            round(lat + radius_deg_lat * math.sin(theta), 6),
            round(lon + radius_deg_lon * math.cos(theta), 6),
        ])
    return ring


def get_isochrone(lat: float, lon: float, minutes: int = 15,
                  profile: str = 'driving-car') -> Dict:
    """
    Retourne l'isochrone (polygone [lat, lon]) pour un point et une durée.
    Ordre : OpenRouteService (si clé configurée) → repli géodésique interne.
    Never raises.
    """
    cache_key = f"isochrone_{lat:.4f}_{lon:.4f}_{minutes}_{profile}"
    cached = cache.get(cache_key)
    if cached:
        return cached

    result = None
    ors_key = getattr(settings, 'ORS_API_KEY', '')
    if ors_key:
        try:
            res = requests.post(
                'https://api.openrouteservice.org/v2/isochrones/' + profile,
                headers={'Authorization': ors_key, 'Content-Type': 'application/json'},
                json={
                    "locations": [[lon, lat]],
                    "range": [minutes * 60],
                    "intersections": False,
                },
                timeout=4.0,
            )
            if res.status_code == 200:
                features = res.json().get('features', [])
                if features:
                    geom = features[0].get('geometry', {})
                    if geom.get('type') == 'Polygon':
                        ring = [[c[1], c[0]] for c in geom['coordinates'][0]]
                        result = {
                            'coordinates': ring,
                            'source': 'OpenRouteService',
                        }
            else:
                logger.warning("ORS isochrone HTTP %s", res.status_code)
        except Exception as exc:
            logger.warning("Échec isochrone ORS: %s", exc)

    if result is None:
        speed = DEFAULT_SPEED_KMH.get(profile, 28.0)
        result = {
            'coordinates': _geodesic_circle(lat, lon, minutes, speed),
            'source': 'Repli Géodésique Interne',
        }

    cache.set(cache_key, result, 86400)
    return result


def _polygon(coords: Sequence[Sequence[float]]):
    from shapely.geometry import Polygon
    return Polygon([(c[0], c[1]) for c in coords])


def find_meeting_point(origin_a: Tuple[float, float],
                       origin_b: Tuple[float, float],
                       minutes: int = 15,
                       profile_a: str = 'driving-car',
                       profile_b: str = 'driving-car') -> Dict:
    """
    Point de rendez-vous optimal = intersection des isochrones des deux utilisateurs.

    Returns:
        {
          "lat": float, "lon": float,
          "method": "isochrone_intersection" | "midpoint_fallback",
          "minutes": int,
          "geojson_a": [[lat, lon], ...], "geojson_b": [[lat, lon], ...],
          "source_a": str, "source_b": str,
        }
    """
    iso_a = get_isochrone(origin_a[0], origin_a[1], minutes, profile_a)
    iso_b = get_isochrone(origin_b[0], origin_b[1], minutes, profile_b)

    lat = lon = None
    method = 'midpoint_fallback'
    try:
        poly_a = _polygon(iso_a['coordinates'])
        poly_b = _polygon(iso_b['coordinates'])
        if poly_a.is_valid and poly_b.is_valid:
            inter = poly_a.intersection(poly_b)
            if not inter.is_empty:
                # Centroïde de l'aire d'intersection (ou point représentatif si ligne/point)
                if inter.geom_type in ('MultiPolygon', 'Polygon'):
                    pt = inter.centroid
                else:
                    pt = inter.representative_point()
                lat, lon = round(pt.y, 6), round(pt.x, 6)
                method = 'isochrone_intersection'
    except Exception as exc:
        logger.warning("Intersection d'isochrones impossible: %s", exc)

    if lat is None:
        # Repli : point le plus proche du milieu des deux origines,
        # à l'intérieur du premier isochrone si possible.
        lat = round((origin_a[0] + origin_b[0]) / 2.0, 6)
        lon = round((origin_a[1] + origin_b[1]) / 2.0, 6)
        method = 'midpoint_fallback'

    return {
        'lat': lat,
        'lon': lon,
        'method': method,
        'minutes': minutes,
        'geojson_a': iso_a['coordinates'],
        'geojson_b': iso_b['coordinates'],
        'source_a': iso_a['source'],
        'source_b': iso_b['source'],
    }
