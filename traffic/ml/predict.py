from datetime import datetime
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from django.utils import timezone

from traffic.context import is_holiday
from traffic.models import MonitoringPoint

from .features import add_features
from .train import MODEL_PATH


class ModelNotTrained(Exception):
    pass


@lru_cache(maxsize=1)
def _bundle():
    """Le modèle est chargé UNE seule fois par processus."""
    if not MODEL_PATH.exists():
        raise ModelNotTrained('Lance : python manage.py train_traffic_model')
    return joblib.load(MODEL_PATH)


def reload_model():
    _bundle.cache_clear()


def _predict(rows):
    b = _bundle()
    df = pd.DataFrame(rows)
    tz = timezone.get_current_timezone_name()
    df['ts'] = pd.to_datetime(df['dt'], utc=True).dt.tz_convert(tz)
    df = add_features(df)
    df['point_id'] = pd.Categorical(df['point_id'], categories=b['point_ids'])
    return np.clip(b['model'].predict(df[b['features']]), 0, 1)


def _aware(dt):
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def predict_congestion(point_id, dt, precipitation_mm=0.0, holiday=None):
    """Congestion prévue (0 = fluide, 1 = bloqué) pour un point à un instant donné."""
    dt = _aware(dt)
    if holiday is None:
        holiday = is_holiday(timezone.localtime(dt).date())
    row = {'point_id': point_id, 'dt': dt,
           'precipitation_mm': precipitation_mm, 'is_holiday': holiday}
    return round(float(_predict([row])[0]), 4)


def predict_all_points(dt, precipitation_mm=0.0):
    """Prévision pour tous les points actifs (sert à la carte de chaleur)."""
    dt = _aware(dt)
    holiday = is_holiday(timezone.localtime(dt).date())
    points = list(MonitoringPoint.objects.filter(is_active=True))
    rows = [{'point_id': p.id, 'dt': dt, 'precipitation_mm': precipitation_mm,
             'is_holiday': holiday} for p in points]
    preds = _predict(rows)
    return [{'point': p.name, 'lat': p.latitude, 'lon': p.longitude,
             'congestion': round(float(c), 4)} for p, c in zip(points, preds)]


def predict_batch(rows):
    """Prévisions vectorisées. rows = dicts {point_id, dt, precipitation_mm, is_holiday}.
    Sert à comparer l'historique réel à la prévision (un seul appel au modèle)."""
    if not rows:
        return []
    rows = [{**r, 'dt': _aware(r['dt'])} for r in rows]
    return [round(float(c), 4) for c in _predict(rows)]