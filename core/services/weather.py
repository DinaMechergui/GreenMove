"""
Service météo écologique utilisant l'API gratuite Open-Meteo pour le Grand Tunis.
Intègre une mise en cache Django de 30 minutes et un mode secours automatique.
"""
import logging
from typing import Dict, Any
import requests
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

# Coordonnées du Grand Tunis (Avenue Habib Bourguiba)
TUNIS_LAT = 36.8065
TUNIS_LON = 10.1815

# Correspondance des codes météo WMO vers descriptions et icônes
WMO_WEATHER_MAP = {
    0: ("Ciel dégagé", "bi-sun-fill text-warning"),
    1: ("Principalement dégagé", "bi-sun text-warning"),
    2: ("Partiellement nuageux", "bi-cloud-sun text-warning"),
    3: ("Couvert", "bi-cloud text-secondary"),
    45: ("Brouillard", "bi-cloud-fog text-secondary"),
    48: ("Brouillard givrant", "bi-cloud-fog text-secondary"),
    51: ("Bruine légère", "bi-cloud-drizzle text-info"),
    53: ("Bruine modérée", "bi-cloud-drizzle text-info"),
    55: ("Bruine dense", "bi-cloud-drizzle text-info"),
    61: ("Pluie légère", "bi-cloud-rain text-primary"),
    63: ("Pluie modérée", "bi-cloud-rain-heavy text-primary"),
    65: ("Pluie forte", "bi-cloud-rain-heavy text-primary"),
    80: ("Averses légères", "bi-cloud-rain text-primary"),
    81: ("Averses modérées", "bi-cloud-rain text-primary"),
    82: ("Averses violentes", "bi-cloud-lightning-rain text-danger"),
    95: ("Orage", "bi-cloud-lightning text-danger"),
}

DEFAULT_FALLBACK_WEATHER: Dict[str, Any] = {
    "city": "Tunis",
    "temperature": 22.5,
    "apparent_temperature": 23.0,
    "humidity": 55,
    "wind_speed": 14.2,
    "condition": "Agréable pour la mobilité douce (Vélo & Marche)",
    "description": "Ciel dégagé",
    "icon_class": "bi-sun-fill text-warning",
    "eco_tip": "Conditions optimales pour les mobilités douces et le covoiturage vert aujourd'hui à Tunis !",
    "is_fallback": True,
}


def get_tunis_weather() -> Dict[str, Any]:
    """
    Récupère la météo courante pour Tunis depuis Open-Meteo.
    Utilise le cache Django pour éviter les requêtes excessives.
    Ne lève jamais d'exception et fournit un fallback transparent.
    """
    cache_key = "greenmove_tunis_weather"
    cached = cache.get(cache_key)
    if cached:
        return cached

    url = getattr(settings, 'OPEN_METEO_API_URL', 'https://api.open-meteo.com/v1/forecast')
    params = {
        'latitude': TUNIS_LAT,
        'longitude': TUNIS_LON,
        'current': 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m',
        'timezone': 'Africa/Tunis',
    }

    try:
        response = requests.get(url, params=params, timeout=3.5)
        if response.status_code == 200:
            data = response.json().get('current', {})
            weather_code = data.get('weather_code', 0)
            desc, icon = WMO_WEATHER_MAP.get(weather_code, ("Temps clair", "bi-sun text-warning"))

            temp = data.get('temperature_2m', 22.0)
            app_temp = data.get('apparent_temperature', temp)
            wind = data.get('wind_speed_10m', 12.0)
            humidity = data.get('relative_humidity_2m', 50)

            # Recommandation éco-mobilité selon la météo
            if weather_code in [0, 1, 2] and temp <= 28:
                eco_tip = "Temps splendide : parfait pour trottinette, vélo ou marche vers le métro !"
            elif weather_code in [61, 63, 65, 80, 81, 82, 95]:
                eco_tip = "Risque d'averses : privilégiez le covoiturage partagé via MobilityMatch."
            else:
                eco_tip = "Bonnes conditions : optimisez vos trajets avec GreenMove."

            result = {
                "city": "Grand Tunis",
                "temperature": round(temp, 1),
                "apparent_temperature": round(app_temp, 1),
                "humidity": humidity,
                "wind_speed": round(wind, 1),
                "condition": "Idéal pour mobilité partagée",
                "description": desc,
                "icon_class": icon,
                "eco_tip": eco_tip,
                "is_fallback": False,
            }
            # Mettre en cache pour 1800 secondes (30 min)
            cache.set(cache_key, result, 1800)
            return result
    except Exception as exc:
        logger.warning(f"Échec de l'appel Open-Meteo pour Tunis : {exc}. Utilisation du fallback.")

    return DEFAULT_FALLBACK_WEATHER
