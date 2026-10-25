"""
Lecture et validation des paramètres de requête.
Partagé par l'API REST et les vues HTML (formulaire "meilleur moment").
Toute erreur lève ParamError avec un message français clair.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from traffic.models import MonitoringPoint

MAX_RANGE = timedelta(hours=12)


class ParamError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def get_int(params, name, default=None, min_value=None, max_value=None, label=None):
    label = label or name
    raw = params.get(name)
    if raw in (None, ''):
        if default is None:
            raise ParamError(f"Le paramètre « {label} » est obligatoire.")
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ParamError(f"Le paramètre « {label} » doit être un nombre entier.")
    if min_value is not None and value < min_value or max_value is not None and value > max_value:
        raise ParamError(f"Le paramètre « {label} » doit être compris entre {min_value} et {max_value}.")
    return value


def get_float(params, name, default, min_value, max_value):
    raw = params.get(name)
    if raw in (None, ''):
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        raise ParamError(f"Le paramètre « {name} » doit être un nombre décimal.")
    if not min_value <= value <= max_value:
        raise ParamError(f"Le paramètre « {name} » doit être compris entre {min_value} et {max_value}.")
    return value


def get_datetime(params, name, required=False):
    """ISO 8601 ('2026-10-26T08:30', avec ou sans fuseau). Sans fuseau : heure de Tunis.
    Retourne None si absent et non obligatoire."""
    raw = (params.get(name) or '').strip()
    if not raw:
        if required:
            raise ParamError(f"Le paramètre « {name} » est obligatoire (format ISO, ex. 2026-10-26T08:00).")
        return None
    # Un '+' non encodé dans l'URL devient un espace : on le restaure.
    raw = raw.replace(' ', '+') if 'T' in raw else raw
    try:
        dt = parse_datetime(raw)
        if dt is None:
            d = parse_date(raw)
            dt = datetime.combine(d, time.min) if d else None
    except ValueError:
        dt = None
    if dt is None:
        raise ParamError(f"Le paramètre « {name} » n'est pas une date valide (format ISO, ex. 2026-10-26T08:00).")
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def get_choice(params, name, choices, default):
    value = params.get(name) or default
    if value not in choices:
        raise ParamError(f"Le paramètre « {name} » doit valoir : {', '.join(choices)}.")
    return value


def get_point(params, name, label=None):
    point_id = get_int(params, name, label=label)
    try:
        return MonitoringPoint.objects.get(pk=point_id, is_active=True)
    except MonitoringPoint.DoesNotExist:
        raise ParamError(f"Point de surveillance {point_id} introuvable.", status=404)


def parse_best_time(params):
    """Valide les paramètres de best_departure. Retourne (origin, dest, start, end, step)."""
    origin = get_point(params, 'origin', 'origin (départ)')
    dest = get_point(params, 'destination', 'destination (arrivée)')
    if origin.pk == dest.pk:
        raise ParamError("Le point de départ et le point d'arrivée doivent être différents.")
    start = get_datetime(params, 'start', required=True)
    end = get_datetime(params, 'end', required=True)
    if start >= end:
        raise ParamError("L'heure de début doit être antérieure à l'heure de fin.")
    if end - start > MAX_RANGE:
        raise ParamError("La plage horaire ne peut pas dépasser 12 heures.")
    step = get_int(params, 'step', default=15, min_value=5, max_value=60)
    return origin, dest, start, end, step
