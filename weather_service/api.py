"""
Endpoints REST météo (préfixe /api/weather/), tous en GET.
Erreurs : {'error': '...'} ; 400 si paramètre invalide, 503 si Open-Meteo indisponible.
"""
from functools import wraps

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from . import services

TAGS = ['Météo']
WEATHER_DOWN = "Service météo (Open-Meteo) momentanément indisponible. Réessayez dans quelques minutes."
MODES = ('walk', 'bike')

ErrorSerializer = inline_serializer('WeatherError', {'error': serializers.CharField()})
ERRORS = {200: OpenApiTypes.OBJECT, 400: ErrorSerializer, 503: ErrorSerializer}
LAT_LON = [
    OpenApiParameter('lat', float, description='latitude (défaut : Tunis 36.8065)'),
    OpenApiParameter('lon', float, description='longitude (défaut : Tunis 10.1815)'),
]
MODE = OpenApiParameter('mode', str, enum=list(MODES), description='walk (marche) ou bike (vélo)')


class ParamError(Exception):
    pass


def _float(params, name, default, lo, hi):
    raw = params.get(name)
    if raw in (None, ''):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ParamError(f"Le paramètre « {name} » doit être un nombre décimal.")
    if not lo <= value <= hi:
        raise ParamError(f"Le paramètre « {name} » doit être compris entre {lo} et {hi}.")
    return value


def _coords(params):
    return (_float(params, 'lat', services.DEFAULT_COORDS[0], -90, 90),
            _float(params, 'lon', services.DEFAULT_COORDS[1], -180, 180))


def _mode(params):
    mode = params.get('mode') or 'walk'
    if mode not in MODES:
        raise ParamError("Le paramètre « mode » doit valoir walk ou bike.")
    return mode


def handle_errors(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ParamError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except services.WeatherAPIError:
            return Response({'error': WEATHER_DOWN}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
    return wrapper


@extend_schema(tags=TAGS, summary='Score de confort marche / vélo (0-100)',
               parameters=[*LAT_LON, MODE,
                           OpenApiParameter('hours_ahead', int, description='0 à 47, défaut 0')],
               responses=ERRORS)
@api_view(['GET'])
@handle_errors
def comfort(request):
    lat, lon = _coords(request.query_params)
    raw = request.query_params.get('hours_ahead') or '0'
    try:
        hours = int(raw)
    except ValueError:
        raise ParamError("Le paramètre « hours_ahead » doit être un nombre entier.")
    if not 0 <= hours <= 47:
        raise ParamError("Le paramètre « hours_ahead » doit être compris entre 0 et 47.")
    return Response(services.get_comfort_score(lat, lon, hours, _mode(request.query_params)))


@extend_schema(tags=TAGS, summary='Alerte pluie dans les 30 prochaines minutes', parameters=LAT_LON,
               responses=ERRORS)
@api_view(['GET'])
@handle_errors
def rain_alert(request):
    lat, lon = _coords(request.query_params)
    return Response(services.rain_alert(lat, lon))


@extend_schema(tags=TAGS, summary="Qualité de l'air (indice européen)", parameters=LAT_LON,
               responses=ERRORS)
@api_view(['GET'])
@handle_errors
def air_quality(request):
    lat, lon = _coords(request.query_params)
    return Response(services.get_air_quality(lat, lon))


@extend_schema(tags=TAGS, summary='Meilleures heures des prochaines 24 h', parameters=[*LAT_LON, MODE],
               responses=ERRORS)
@api_view(['GET'])
@handle_errors
def best_hours(request):
    lat, lon = _coords(request.query_params)
    mode = _mode(request.query_params)
    return Response({'mode': mode, 'hours': services.best_hours(lat, lon, mode)})
