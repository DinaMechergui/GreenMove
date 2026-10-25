import requests
from django.conf import settings

FLOW_URL = (
    'https://api.tomtom.com/traffic/services/4/'
    'flowSegmentData/absolute/10/json'
)


class TrafficAPIError(Exception):
    pass


def fetch_flow(latitude, longitude):
    """Interroge TomTom pour un point (utilisé seulement si TRAFFIC_SOURCE=tomtom)."""
    if not settings.TOMTOM_API_KEY:
        raise TrafficAPIError('TOMTOM_API_KEY manquante dans .env')
    try:
        r = requests.get(
            FLOW_URL,
            params={'key': settings.TOMTOM_API_KEY, 'point': f'{latitude},{longitude}'},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()['flowSegmentData']
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise TrafficAPIError(str(exc)) from exc

    current = data['currentSpeed']
    free = data['freeFlowSpeed']
    congestion = max(0.0, min(1.0, 1 - current / free)) if free else 0.0
    return {
        'current_speed': current,
        'free_flow_speed': free,
        'congestion': round(congestion, 4),
    }