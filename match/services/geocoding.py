"""
Service de géocodage utilisant l'API Nominatim OpenStreetMap.
Respecte la politique d'utilisation OSM :
- Maximum 1 requête par seconde.
- User-Agent explicite obligatoire.
- Mise en cache agressive (24h) via Django Cache.
- Dictionnaire de secours pour les emplacements du Grand Tunis.
"""
import time
import logging
from typing import Optional, Tuple, Dict, Any
import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Base locale de secours pour le Grand Tunis
TUNIS_LOCAL_GEODATA: Dict[str, Tuple[float, float]] = {
    "lac 2": (36.8392, 10.2447),
    "les berges du lac 2": (36.8392, 10.2447),
    "lac 1": (36.8320, 10.2280),
    "ariana": (36.8625, 10.1956),
    "ariana centre": (36.8625, 10.1956),
    "la marsa": (36.8782, 10.3247),
    "marsa plage": (36.8782, 10.3247),
    "le bardo": (36.8090, 10.1415),
    "bardo": (36.8090, 10.1415),
    "manouba": (36.8118, 10.0632),
    "campus manouba": (36.8118, 10.0632),
    "centre-ville": (36.8000, 10.1800),
    "tunis centre-ville": (36.8000, 10.1800),
    "bourguiba": (36.8000, 10.1800),
    "ben arous": (36.7531, 10.2189),
    "carthage": (36.8530, 10.3315),
    "ennasr": (36.8710, 10.1580),
    "el menzah": (36.8450, 10.1750),
    "menzah": (36.8450, 10.1750),
    "megrine": (36.7680, 10.2310),
    "mégrine": (36.7680, 10.2310),
    "sidi bou said": (36.8700, 10.3420),
    "la goulette": (36.8180, 10.3050),
    "le kram": (36.8330, 10.3170),
}

_last_request_timestamp = 0.0


def _rate_limit_nominatim():
    """Garantit un intervalle minimum d'au moins 1,1 seconde entre requêtes OSM."""
    global _last_request_timestamp
    elapsed = time.time() - _last_request_timestamp
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _last_request_timestamp = time.time()


def geocode_address(query: str) -> Optional[Tuple[float, float]]:
    """
    Géocode une adresse en coordonnées (latitude, longitude).
    Vérifie d'abord le cache, puis la base locale de secours, puis interroge Nominatim.
    Ne lève jamais d'exception.
    """
    if not query or not query.strip():
        return None

    cleaned_query = query.strip().lower()
    cache_key = f"nominatim_geocode_{cleaned_query.replace(' ', '_')}"

    # 1. Vérification dans le cache Django
    cached_coords = cache.get(cache_key)
    if cached_coords:
        return cached_coords

    # 2. Vérification dans la base locale tunisienne de secours
    for key, coords in TUNIS_LOCAL_GEODATA.items():
        if key in cleaned_query:
            cache.set(cache_key, coords, 86400)
            return coords

    # 3. Interrogation de Nominatim OpenStreetMap avec respect du rate limit
    user_agent = getattr(settings, 'NOMINATIM_USER_AGENT', 'GreenMove-Platform/1.0 (contact@greenmove.tn)')
    headers = {'User-Agent': user_agent}
    params = {
        'q': f"{query}, Tunis, Tunisie",
        'format': 'json',
        'limit': 1,
        'countrycodes': 'tn',
    }

    try:
        _rate_limit_nominatim()
        response = requests.get(
            'https://nominatim.openstreetmap.org/search',
            params=params,
            headers=headers,
            timeout=4.0
        )
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                lat = float(data[0]['lat'])
                lon = float(data[0]['lon'])
                coords = (lat, lon)
                # Sauvegarde en cache pendant 24h
                cache.set(cache_key, coords, 86400)
                return coords
    except Exception as exc:
        logger.warning(f"Nominatim indisponible pour '{query}': {exc}. Utilisation des coordonnées par défaut de Tunis.")

    # Fallback par défaut sur le centre de Tunis si introuvable
    default_coords = (36.8000, 10.1800)
    cache.set(cache_key, default_coords, 3600)
    return default_coords
