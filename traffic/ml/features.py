import numpy as np
import pandas as pd
from django.utils import timezone

from traffic.models import TrafficSnapshot

FEATURES = [
    'point_id', 'minute_of_day', 'hour_sin', 'hour_cos',
    'dow', 'is_weekend', 'is_holiday', 'precipitation_mm',
]
TARGET = 'congestion'


def add_features(df):
    """Ajoute les features à partir de la colonne 'ts' (datetime local)."""
    ts = df['ts']
    df['minute_of_day'] = ts.dt.hour * 60 + ts.dt.minute
    angle = 2 * np.pi * df['minute_of_day'] / 1440
    df['hour_sin'] = np.sin(angle)  # 23h30 est proche de 0h : encodage cyclique
    df['hour_cos'] = np.cos(angle)
    df['dow'] = ts.dt.dayofweek     # 0 = lundi
    df['is_weekend'] = (df['dow'] >= 5).astype(int)
    df['is_holiday'] = df['is_holiday'].astype(int)
    return df


def load_dataframe():
    """Charge tous les snapshots en DataFrame trié par date."""
    rows = list(TrafficSnapshot.objects.values(
        'point_id', 'timestamp', 'congestion', 'precipitation_mm', 'is_holiday'))
    if not rows:
        raise ValueError('Aucun snapshot : lance generate_synthetic_history.')
    df = pd.DataFrame(rows)
    tz = timezone.get_current_timezone_name()
    df['ts'] = pd.to_datetime(df['timestamp'], utc=True).dt.tz_convert(tz)
    df = add_features(df).sort_values('ts').reset_index(drop=True)
    return df