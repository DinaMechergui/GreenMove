from functools import lru_cache

import requests
from django.conf import settings

TUNIS = (36.8065, 10.1815)


def hourly_precipitation(days):
    """{'2026-10-25T08:00': 0.4, ...} pour les `days` derniers jours (max 92) + aujourd'hui."""
    try:
        r = requests.get(settings.OPEN_METEO_API_URL, params={
            'latitude': TUNIS[0], 'longitude': TUNIS[1],
            'hourly': 'precipitation', 'past_days': min(days, 92),
            'forecast_days': 1, 'timezone': 'Africa/Tunis',
        }, timeout=20)
        r.raise_for_status()
        h = r.json()['hourly']
        return dict(zip(h['time'], h['precipitation']))
    except (requests.RequestException, KeyError, ValueError):
        return {}


def current_precipitation():
    try:
        r = requests.get(settings.OPEN_METEO_API_URL, params={
            'latitude': TUNIS[0], 'longitude': TUNIS[1],
            'current': 'precipitation', 'timezone': 'Africa/Tunis',
        }, timeout=10)
        r.raise_for_status()
        return float(r.json()['current']['precipitation'])
    except (requests.RequestException, KeyError, ValueError, TypeError):
        return 0.0


@lru_cache(maxsize=8)
def _holidays(year):
    try:
        r = requests.get(f'https://date.nager.at/api/v3/PublicHolidays/{year}/TN', timeout=10)
        r.raise_for_status()
        return frozenset(item['date'] for item in r.json())
    except (requests.RequestException, KeyError, ValueError):
        return frozenset()


def is_holiday(d):
    return d.isoformat() in _holidays(d.year)