import json
from datetime import datetime
from pathlib import Path

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, root_mean_squared_error

from .features import FEATURES, TARGET, load_dataframe

ARTIFACT_DIR = Path(__file__).resolve().parent / 'artifacts'
MODEL_PATH = ARTIFACT_DIR / 'traffic_model.joblib'
METRICS_PATH = ARTIFACT_DIR / 'metrics.json'


def compute_metrics(y, pred):
    y, pred = np.asarray(y), np.asarray(pred)
    mask = y >= 0.1  # MAPE explose quand y est proche de 0 : on l'exclut
    return {
        'MAE': round(float(mean_absolute_error(y, pred)), 4),
        'RMSE': round(float(root_mean_squared_error(y, pred)), 4),
        'MAPE_%': round(float(np.mean(np.abs((y[mask] - pred[mask]) / y[mask])) * 100), 2),
    }


def train(test_days=10):
    df = load_dataframe()
    point_ids = sorted(df['point_id'].unique().tolist())
    df['point_id'] = pd.Categorical(df['point_id'], categories=point_ids)

    # Split CHRONOLOGIQUE : on entraîne sur le passé, on teste sur les derniers jours
    cutoff = df['ts'].max() - pd.Timedelta(days=test_days)
    train_df, test_df = df[df['ts'] <= cutoff], df[df['ts'] > cutoff].copy()

    # Baseline : moyenne de congestion par (point, heure) sur l'entraînement
    base = train_df.assign(hour=train_df['minute_of_day'] // 60)
    means = (base.groupby(['point_id', 'hour'], observed=True)[TARGET]
             .mean().rename('base').reset_index())
    t = test_df.assign(hour=test_df['minute_of_day'] // 60)
    t = t.merge(means, on=['point_id', 'hour'], how='left')
    baseline_pred = t['base'].fillna(train_df[TARGET].mean()).to_numpy()

    model = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        random_state=42, verbose=-1)
    model.fit(train_df[FEATURES], train_df[TARGET])
    pred = np.clip(model.predict(test_df[FEATURES]), 0, 1)

    importance = dict(zip(FEATURES, model.booster_.feature_importance('gain').round(1).tolist()))
    metrics = {
        'trained_at': datetime.now().isoformat(timespec='seconds'),
        'train_rows': int(len(train_df)), 'test_rows': int(len(test_df)),
        'split': f'test = {test_days} derniers jours',
        'baseline_point_hour': compute_metrics(test_df[TARGET], baseline_pred),
        'lightgbm': compute_metrics(test_df[TARGET], pred),
        'feature_importance_gain': importance,
    }

    ARTIFACT_DIR.mkdir(exist_ok=True)
    joblib.dump({'model': model, 'features': FEATURES, 'point_ids': point_ids,
                 'metrics': metrics}, MODEL_PATH)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding='utf-8')
    return metrics