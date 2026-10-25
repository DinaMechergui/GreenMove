import hashlib
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

AIR_QUALITY_URL = 'https://air-quality-api.open-meteo.com/v1/air-quality'
DEFAULT_COORDS = (36.8065, 10.1815)  # Tunis
TZ = 'Africa/Tunis'

TTL_FORECAST = 30 * 60
TTL_RAIN = 5 * 60
TTL_AIR = 30 * 60


class WeatherAPIError(Exception):
    pass


def _get(url, params, ttl):
    """Appel Open-Meteo avec cache. Les coordonnées sont arrondies pour réutiliser le cache."""
    key = 'wx:' + hashlib.md5((url + repr(sorted(params.items()))).encode()).hexdigest()
    cached = cache.get(key)
    if cached is not None:
        return cached
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Open-Meteo indisponible : %s', exc)
        raise WeatherAPIError(str(exc)) from exc
    cache.set(key, data, ttl)
    return data


def _round(lat, lon):
    return round(lat, 2), round(lon, 2)


# ---------- 1. Prévisions horaires ----------
def get_hourly_forecast(lat=DEFAULT_COORDS[0], lon=DEFAULT_COORDS[1], hours=24):
    """Liste de dicts, à partir de l'heure courante."""
    lat, lon = _round(lat, lon)
    data = _get(settings.OPEN_METEO_API_URL, {
        'latitude': lat, 'longitude': lon, 'timezone': TZ,
        'hourly': 'temperature_2m,apparent_temperature,precipitation,'
                  'precipitation_probability,wind_speed_10m,uv_index',
        'forecast_hours': hours,
    }, TTL_FORECAST)
    try:
        h = data['hourly']
        return [{
            'time': h['time'][i],
            'temperature': h['temperature_2m'][i],
            'feels_like': h['apparent_temperature'][i],
            'precipitation_mm': h['precipitation'][i] or 0.0,
            'rain_probability': h['precipitation_probability'][i] or 0,
            'wind_kmh': h['wind_speed_10m'][i] or 0.0,
            'uv': h['uv_index'][i] or 0.0,
        } for i in range(len(h['time']))]
    except (KeyError, IndexError, TypeError) as exc:
        raise WeatherAPIError(f'Réponse inattendue : {exc}') from exc


# ---------- 2. Score de confort ----------
def comfort_score(temperature, precipitation_mm, wind_kmh, uv, rain_probability=0, mode='walk'):
    """Score de 0 à 100 (fonction pure, facile à tester)."""
    low, high = (18, 24) if mode == 'walk' else (16, 22)
    score = 100.0
    if temperature < low:
        score -= (low - temperature) * 3
    elif temperature > high:
        score -= (temperature - high) * 3.5
    score -= min(60, precipitation_mm * 30)
    score -= rain_probability * 0.15
    wind_limit = 20 if mode == 'walk' else 15
    if wind_kmh > wind_limit:
        score -= (wind_kmh - wind_limit) * (1.5 if mode == 'walk' else 2)
    if uv > 7:
        score -= (uv - 7) * 4
    return int(max(0, min(100, round(score))))


def comfort_label(score):
    if score >= 80:
        return 'excellent'
    if score >= 60:
        return 'bon'
    if score >= 40:
        return 'moyen'
    return 'déconseillé'


def get_comfort_score(lat=DEFAULT_COORDS[0], lon=DEFAULT_COORDS[1], hours_ahead=0, mode='walk'):
    """Confort marche ('walk') ou vélo ('bike') dans `hours_ahead` heures."""
    forecast = get_hourly_forecast(lat, lon, hours=max(24, hours_ahead + 1))
    f = forecast[min(hours_ahead, len(forecast) - 1)]
    score = comfort_score(f['feels_like'], f['precipitation_mm'], f['wind_kmh'],
                          f['uv'], f['rain_probability'], mode)
    return {'time': f['time'], 'mode': mode, 'score': score,
            'label': comfort_label(score), 'conditions': f}


def best_hours(lat=DEFAULT_COORDS[0], lon=DEFAULT_COORDS[1], mode='walk', top=3):
    """Les `top` meilleures heures des prochaines 24 h (utile à l'EcoPlanner)."""
    scored = []
    for f in get_hourly_forecast(lat, lon, hours=24):
        s = comfort_score(f['feels_like'], f['precipitation_mm'], f['wind_kmh'],
                          f['uv'], f['rain_probability'], mode)
        scored.append({'time': f['time'], 'score': s})
    return sorted(scored, key=lambda x: -x['score'])[:top]


# ---------- 3. Alerte pluie ----------
def rain_alert(lat=DEFAULT_COORDS[0], lon=DEFAULT_COORDS[1], horizon_minutes=30):
    """Pluie attendue dans les `horizon_minutes` prochaines minutes ?"""
    lat, lon = _round(lat, lon)
    steps = max(1, horizon_minutes // 15)
    data = _get(settings.OPEN_METEO_API_URL, {
        'latitude': lat, 'longitude': lon, 'timezone': TZ,
        'minutely_15': 'precipitation', 'forecast_minutely_15': steps + 1,
    }, TTL_RAIN)
    try:
        times = data['minutely_15']['time']
        values = data['minutely_15']['precipitation']
    except KeyError as exc:
        raise WeatherAPIError(f'Réponse inattendue : {exc}') from exc

    for i, (t, mm) in enumerate(zip(times, values)):
        if mm and mm >= 0.1:
            minutes = i * 15
            msg = ('Il pleut en ce moment.' if minutes == 0
                   else f'La pluie arrive dans environ {minutes} min.')
            return {'alert': True, 'minutes': minutes, 'precipitation_mm': mm, 'message': msg}
    return {'alert': False, 'minutes': None, 'precipitation_mm': 0.0,
            'message': f'Pas de pluie prévue dans les {horizon_minutes} prochaines minutes.'}


# ---------- 4. Qualité de l'air ----------
def _aqi_label(aqi):
    if aqi is None:
        return 'inconnue'
    for limit, label in ((20, 'très bonne'), (40, 'bonne'), (60, 'moyenne'),
                         (80, 'médiocre'), (100, 'mauvaise')):
        if aqi <= limit:
            return label
    return 'très mauvaise'


def get_air_quality(lat=DEFAULT_COORDS[0], lon=DEFAULT_COORDS[1]):
    lat, lon = _round(lat, lon)
    data = _get(AIR_QUALITY_URL, {
        'latitude': lat, 'longitude': lon, 'timezone': TZ,
        'current': 'european_aqi,pm10,pm2_5',
    }, TTL_AIR)
    try:
        cur = data['current']
    except KeyError as exc:
        raise WeatherAPIError(f'Réponse inattendue : {exc}') from exc
    aqi = cur.get('european_aqi')
    return {'aqi': aqi, 'label': _aqi_label(aqi), 'pm10': cur.get('pm10'),
            'pm2_5': cur.get('pm2_5'), 'alert': aqi is not None and aqi > 60}