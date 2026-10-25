"""
Endpoints REST du module Traffic (tous en GET, JSON).

Permissions et throttling : configuration DRF globale du projet
(IsAuthenticatedOrReadOnly + AnonRateThrottle/UserRateThrottle), donc lecture publique.
Erreurs : {'error': '<message en français>'} avec 400 / 404 / 503.
"""
import logging
from datetime import timedelta
from functools import wraps

from django.conf import settings
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from traffic.best_time import best_departure
from traffic.levels import level, level_code
from traffic.ml.predict import ModelNotTrained, predict_all_points, predict_batch, predict_congestion
from traffic.models import MonitoringPoint, TrafficSnapshot
from weather_service.services import WeatherAPIError, get_hourly_forecast

from . import serializers as s
from .params import ParamError, get_datetime, get_int, get_point, parse_best_time

logger = logging.getLogger(__name__)

MODEL_NOT_TRAINED = "Modèle non entraîné. Lancez : python manage.py train_traffic_model"
WEATHER_DOWN = "Service météo (Open-Meteo) momentanément indisponible. Réessayez dans quelques minutes."
TAGS = ['Traffic']
ERRORS = {400: s.ErrorSerializer, 404: s.ErrorSerializer, 503: s.ErrorSerializer}


def error(message, code):
    return Response({'error': message}, status=code)


def handle_errors(view):
    """Traduit les exceptions métier en réponses JSON claires."""
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except ParamError as exc:
            return error(exc.message, exc.status)
        except ModelNotTrained:
            return error(MODEL_NOT_TRAINED, status.HTTP_503_SERVICE_UNAVAILABLE)
        except WeatherAPIError:
            return error(WEATHER_DOWN, status.HTTP_503_SERVICE_UNAVAILABLE)
    return wrapper


def rain_at(dt):
    """(pluie prévue en mm à l'heure de dt, météo disponible ?). Jamais d'exception."""
    try:
        forecast = get_hourly_forecast(hours=48)
    except WeatherAPIError:
        return 0.0, False
    key = timezone.localtime(dt).strftime('%Y-%m-%dT%H')
    for f in forecast:
        if f['time'][:13] == key:
            return float(f['precipitation_mm'] or 0.0), True
    return 0.0, True  # hors de la fenêtre de prévision (passé ou > 48 h)


def _dt_param(description):
    return OpenApiParameter('datetime', OpenApiTypes.DATETIME, description=description)


@extend_schema(tags=TAGS, summary='Points de surveillance actifs',
               responses=s.MonitoringPointSerializer(many=True))
@api_view(['GET'])
def points(request):
    qs = MonitoringPoint.objects.filter(is_active=True).order_by('name')
    return Response(s.MonitoringPointSerializer(qs, many=True).data)


@extend_schema(
    tags=TAGS, summary="Congestion prévue pour un point",
    parameters=[OpenApiParameter('point', int, required=True, description='id du point'),
                _dt_param('ISO 8601, défaut : maintenant (heure de Tunis si sans fuseau)')],
    responses={200: s.ForecastSerializer, **ERRORS})
@api_view(['GET'])
@handle_errors
def forecast(request):
    point = get_point(request.query_params, 'point')
    dt = get_datetime(request.query_params, 'datetime') or timezone.now()
    c = predict_congestion(point.id, dt)
    return Response({
        'point': s.MonitoringPointSerializer(point).data,
        'datetime': timezone.localtime(dt).isoformat(),
        'congestion': c, 'level': level(c), 'level_code': level_code(c),
        'data_source': settings.TRAFFIC_SOURCE,
    })


@extend_schema(
    tags=TAGS, summary='Prévision pour tous les points (carte de chaleur)',
    parameters=[_dt_param('ISO 8601, défaut : maintenant')],
    responses={200: s.HeatmapSerializer, **ERRORS})
@api_view(['GET'])
@handle_errors
def heatmap(request):
    dt = get_datetime(request.query_params, 'datetime') or timezone.now()
    rain, weather_ok = rain_at(dt)
    items = predict_all_points(dt, precipitation_mm=rain)
    for item in items:
        item['level'] = level(item['congestion'])
        item['level_code'] = level_code(item['congestion'])
    return Response({
        'datetime': timezone.localtime(dt).isoformat(),
        'precipitation_mm': rain, 'weather_available': weather_ok,
        'data_source': settings.TRAFFIC_SOURCE, 'points': items,
    })


@extend_schema(
    tags=TAGS, summary='Meilleur moment pour partir',
    parameters=[
        OpenApiParameter('origin', int, required=True),
        OpenApiParameter('destination', int, required=True),
        OpenApiParameter('start', OpenApiTypes.DATETIME, required=True),
        OpenApiParameter('end', OpenApiTypes.DATETIME, required=True,
                         description='plage max 12 h après start'),
        OpenApiParameter('step', int, description='minutes entre deux créneaux (5 à 60, défaut 15)'),
    ],
    responses={200: s.BestTimeSerializer, **ERRORS})
@api_view(['GET'])
@handle_errors
def best_time(request):
    origin, dest, start, end, step = parse_best_time(request.query_params)
    return Response(best_departure(origin.id, dest.id, start, end, step))


@extend_schema(
    tags=TAGS, summary="Historique récent d'un point (+ prévision du modèle)",
    parameters=[OpenApiParameter('point', int, required=True),
                OpenApiParameter('days', int, description='1 à 14, défaut 2')],
    responses={200: s.SnapshotSerializer(many=True), **ERRORS})
@api_view(['GET'])
@handle_errors
def history(request):
    point = get_point(request.query_params, 'point')
    days = get_int(request.query_params, 'days', default=2, min_value=1, max_value=14)

    latest = point.snapshots.order_by('-timestamp').values_list('timestamp', flat=True).first()
    if latest is None:
        return Response({'point': s.MonitoringPointSerializer(point).data, 'days': days,
                         'model_available': False, 'snapshots': []})
    # Si la collecte s'est arrêtée, on montre les derniers jours disponibles.
    now = timezone.now()
    end = now if latest > now - timedelta(days=days) else latest
    snaps = list(TrafficSnapshot.objects.filter(
        point=point, timestamp__gt=end - timedelta(days=days), timestamp__lte=end,
    ).order_by('timestamp'))

    predictions, model_ok = {}, True
    try:
        preds = predict_batch([{'point_id': point.id, 'dt': x.timestamp,
                                'precipitation_mm': x.precipitation_mm,
                                'is_holiday': x.is_holiday} for x in snaps])
        predictions = {x.pk: p for x, p in zip(snaps, preds)}
    except ModelNotTrained:
        model_ok = False

    return Response({
        'point': s.MonitoringPointSerializer(point).data, 'days': days,
        'model_available': model_ok, 'data_source': settings.TRAFFIC_SOURCE,
        'snapshots': s.SnapshotSerializer(snaps, many=True,
                                          context={'predictions': predictions}).data,
    })
