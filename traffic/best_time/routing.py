"""
routing.py : calcule la durée d'un trajet "à vide" (sans embouteillage)
entre deux points GPS.

Pourquoi ? Pour "meilleur moment pour partir", il faut connaître la durée
de base du trajet. Ensuite service.py la multiplie par un coefficient
de congestion prédit par le modèle ML.

Deux niveaux :
  1. OpenRouteService (ORS) : vraie durée routière, si ORS_API_KEY existe
  2. Estimation : distance à vol d'oiseau x 1,3 / 40 km/h
Le programme marche donc même sans clé ni internet.
"""

import logging
import math

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

ORS_URL = 'https://api.openrouteservice.org/v2/directions/driving-car'
FALLBACK_SPEED_KMH = 40  # vitesse moyenne urbaine pour l'estimation de secours


def haversine_km(lat1, lon1, lat2, lon2):
    """Distance à vol d'oiseau (km) entre deux points GPS (formule de haversine)."""
    r = 6371  # rayon de la Terre en km
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def base_duration_minutes(origin, dest):
    """
    Durée du trajet à vide, en minutes.
    Entrées : origin et dest = tuples (latitude, longitude)
    Sortie  : {'minutes': 22.5, 'source': 'openrouteservice' ou 'estimation'}
    """
    # Cache : un trajet déjà calculé est réutilisé (économise le quota ORS,
    # car on calcule un créneau toutes les 15 min pour le même trajet)
    key = f'route:{origin[0]:.4f},{origin[1]:.4f}:{dest[0]:.4f},{dest[1]:.4f}'
    cached = cache.get(key)
    if cached:
        return cached

    result = None

    # Premier choix : ORS, seulement si une clé est configurée dans .env
    if settings.ORS_API_KEY:
        try:
            r = requests.post(
                ORS_URL,
                # ATTENTION : ORS attend (longitude, latitude), l'ordre est inversé
                json={'coordinates': [[origin[1], origin[0]], [dest[1], dest[0]]]},
                headers={'Authorization': settings.ORS_API_KEY},
                timeout=10)
            r.raise_for_status()
            seconds = r.json()['routes'][0]['summary']['duration']
            result = {'minutes': seconds / 60, 'source': 'openrouteservice'}
        except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
            # ORS en panne : on ne plante pas, on passe à l'estimation
            logger.warning('ORS indisponible, repli sur estimation : %s', exc)

    # Plan de secours : distance x 1,3 (les routes ne sont pas des lignes droites)
    # divisée par la vitesse moyenne
    if result is None:
        km = haversine_km(*origin, *dest) * 1.3
        result = {'minutes': km / FALLBACK_SPEED_KMH * 60, 'source': 'estimation'}

    cache.set(key, result, 24 * 3600)  # on garde le résultat 24 h
    return result