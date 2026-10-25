"""
service.py : trouve le meilleur moment pour partir.

Principe :
  1. durée de base du trajet (routing.py)
  2. pour chaque créneau de 15 min : on demande au modèle ML la congestion
     du point de départ et d'arrivée, on en fait la moyenne
  3. durée avec trafic = durée de base x (1 + 1,5 x congestion)
  4. on garde le créneau le plus court et on calcule le gain de temps
"""

from datetime import timedelta

from django.utils import timezone

from traffic.ml.predict import predict_congestion
from traffic.models import MonitoringPoint
from weather_service.services import WeatherAPIError, get_hourly_forecast

from .routing import base_duration_minutes

# Hypothèse du modèle : à congestion 1, le trajet dure 2,5 fois plus longtemps.
# Paramètre à justifier ou calibrer avec de vraies durées.
CONGESTION_FACTOR = 1.5


def _rain_by_hour():
    """Pluie prévue par heure ({'2026-10-26T08': 0.4, ...}) depuis weather_service.
    Si la météo est indisponible, on suppose zéro pluie."""
    try:
        return {f['time'][:13]: f['precipitation_mm'] for f in get_hourly_forecast(hours=48)}
    except WeatherAPIError:
        return {}


def best_departure(origin_id, dest_id, start, end, step=15):
    """
    Compare tous les départs entre `start` et `end` (datetimes), toutes les `step` minutes.
    Retourne le meilleur créneau, le pire, le gain de temps et la liste complète.
    """
    origin = MonitoringPoint.objects.get(pk=origin_id)
    dest = MonitoringPoint.objects.get(pk=dest_id)
    base = base_duration_minutes((origin.latitude, origin.longitude),
                                 (dest.latitude, dest.longitude))
    rain = _rain_by_hour()

    options, t = [], start
    while t <= end:
        local = timezone.localtime(t) if timezone.is_aware(t) else t
        mm = rain.get(local.strftime('%Y-%m-%dT%H'), 0.0)

        # congestion du trajet = moyenne des congestions prévues aux deux extrémités
        c = (predict_congestion(origin.id, t, mm) + predict_congestion(dest.id, t, mm)) / 2
        minutes = base['minutes'] * (1 + CONGESTION_FACTOR * c)

        options.append({
            'departure': local.strftime('%Y-%m-%d %H:%M'),
            'congestion': round(c, 3),
            'duration_min': round(minutes, 1),
            'precipitation_mm': mm,
        })
        t += timedelta(minutes=step)

    best = min(options, key=lambda o: o['duration_min'])
    worst = max(options, key=lambda o: o['duration_min'])
    return {
        'origin': origin.name,
        'destination': dest.name,
        'base_duration_min': round(base['minutes'], 1),
        'duration_source': base['source'],
        'best': best,
        'worst': worst,
        'time_saved_min': round(worst['duration_min'] - best['duration_min'], 1),
        'message': (f"Partez à {best['departure'][11:]} : {best['duration_min']:.0f} min "
                    f"au lieu de {worst['duration_min']:.0f} min à {worst['departure'][11:]}."),
        'options': options,
    }