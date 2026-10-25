"""

1. Matching (classification binaire « bon covoiturage / mauvais ») :
   - Modèle  : score multi-critères `compute_ride_match_score` (seuil 50 %).
   - Baseline: distance seule entre les points de départ (< 3 km).
   Jeu de test synthétique reproductible (seed fixe) autour du Grand Tunis,
   avec des cas difficiles (départ proche mais destination opposée, horaires décalés).
   Métriques : précision, rappel, F1, exactitude, matrice de confusion.

2. Groupes récurrents (clustering) :
   - Modèle  : DBSCAN 4D (départ + arrivée).
   - Baseline: arrondi des départs sur une grille de 0,05° (~5 km).
   Métriques : silhouette et ARI (Adjusted Rand Index) vs vérité terrain.
"""
import math
import random
import time
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Dict, List, Tuple

from .ai_matcher import compute_ride_match_score
from .routing import calculate_haversine_distance

SEED = 42
BASELINE_RADIUS_KM = 3.0      # baseline : départs à moins de 3 km
TUNIS_HUBS = [
    (36.8065, 10.1815),  # Tunis centre
    (36.8530, 10.3230),  # La Marsa
    (36.7400, 10.2300),  # Ben Arous
    (36.8625, 10.1956),  # Ariana
    (36.8380, 10.2400),  # Lac
    (36.7650, 10.0600),  # Manouba
]


def _jitter(point: Tuple[float, float], km: float, rng: random.Random) -> Tuple[float, float]:
    d = km / 111.0
    return point[0] + rng.uniform(-d, d), point[1] + rng.uniform(-d, d)


def _ride(origin, dest, when, rng):
    driver = SimpleNamespace(
        vehicle_type=rng.choice(['ELECTRIC', 'HYBRID', 'THERMAL_ECO', 'NONE']),
        reliability_score=rng.uniform(3.5, 5.0),
        ride_preference='MIXTE', gender='', is_smoker=False,
    )
    return SimpleNamespace(
        origin_lat=origin[0], origin_lon=origin[1],
        destination_lat=dest[0], destination_lon=dest[1],
        polyline_coords=[origin, dest], departure_datetime=when,
        distance_km=max(calculate_haversine_distance(*origin, *dest), 0.5),
        user=driver, estimated_co2_saved=0.0,
    )


def build_match_dataset(n: int = 300, seed: int = SEED) -> List[Dict]:
    """Paires (recherche, trajet candidat, label vérité terrain)."""
    rng = random.Random(seed)
    base = datetime(2026, 10, 26, 8, 0)
    data = []
    for i in range(n):
        o_hub, d_hub = rng.sample(TUNIS_HUBS, 2)
        q_o, q_d = _jitter(o_hub, 1.0, rng), _jitter(d_hub, 1.0, rng)
        q_t = base + timedelta(minutes=rng.randint(-60, 60))
        kind = i % 4
        if kind == 0:      # bon match : même axe, même créneau
            c = _ride(_jitter(q_o, 1.2, rng), _jitter(q_d, 1.2, rng),
                      q_t + timedelta(minutes=rng.randint(-20, 20)), rng)
            label = 1
        elif kind == 1:    # piège baseline : départ proche, destination différente
            other = rng.choice([h for h in TUNIS_HUBS if h not in (o_hub, d_hub)])
            c = _ride(_jitter(q_o, 1.0, rng), _jitter(other, 1.0, rng),
                      q_t + timedelta(minutes=rng.randint(-20, 20)), rng)
            label = 0
        elif kind == 2:    # piège horaire : même axe mais 3 h+ d'écart
            c = _ride(_jitter(q_o, 1.0, rng), _jitter(q_d, 1.0, rng),
                      q_t + timedelta(minutes=rng.choice([-1, 1]) * rng.randint(180, 300)), rng)
            label = 0
        else:              # bon match légèrement décalé (détour modéré)
            c = _ride(_jitter(q_o, 2.0, rng), _jitter(q_d, 2.0, rng),
                      q_t + timedelta(minutes=rng.randint(-35, 35)), rng)
            label = 1
        data.append({'origin': q_o, 'dest': q_d, 'time': q_t, 'ride': c, 'label': label})
    return data


def classification_metrics(y_true: List[int], y_pred: List[int]) -> Dict:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        'precision': round(precision, 3), 'recall': round(recall, 3), 'f1': round(f1, 3),
        'accuracy': round((tp + tn) / max(len(y_true), 1), 3),
        'confusion': {'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn},
    }


def _scores(data: List[Dict]) -> List[int]:
    return [compute_ride_match_score(d['origin'], d['dest'], d['time'], d['ride'])['match_percentage']
            for d in data]


def calibrate_threshold(n: int = 200, seed: int = 7) -> int:
    """Choisit le seuil qui maximise le F1 sur un jeu de CALIBRATION distinct du jeu de test."""
    data = build_match_dataset(n, seed=seed)
    y = [d['label'] for d in data]
    scores = _scores(data)
    return max(range(20, 81, 2),
               key=lambda t: classification_metrics(y, [int(s >= t) for s in scores])['f1'])


def evaluate_matcher(n: int = 300) -> Dict:
    threshold = calibrate_threshold()
    data = build_match_dataset(n)
    y_true = [d['label'] for d in data]
    y_base = []
    start = time.perf_counter()
    scores = _scores(data)
    elapsed_ms = (time.perf_counter() - start) * 1000
    y_model = [int(s >= threshold) for s in scores]
    for d in data:
        r = d['ride']
        dist = calculate_haversine_distance(*d['origin'], r.origin_lat, r.origin_lon)
        y_base.append(int(dist < BASELINE_RADIUS_KM))
    return {
        'n_samples': n,
        'threshold': threshold,
        'model': classification_metrics(y_true, y_model),
        'baseline': classification_metrics(y_true, y_base),
        'avg_latency_ms': round(elapsed_ms / max(n, 1), 3),
    }


def evaluate_clustering(n_groups: int = 5, per_group: int = 12, seed: int = SEED) -> Dict:
    """Silhouette + ARI du DBSCAN 4D vs baseline grille, sur des groupes connus."""
    from sklearn.cluster import DBSCAN
    from sklearn.metrics import adjusted_rand_score, silhouette_score

    rng = random.Random(seed)
    pairs = [tuple(rng.sample(TUNIS_HUBS, 2)) for _ in range(n_groups)]
    X, truth, origins = [], [], []
    lat0, lon0 = TUNIS_HUBS[0]
    m_lon = 111320.0 * math.cos(math.radians(lat0))
    for g, (o, d) in enumerate(pairs):
        for _ in range(per_group):
            oo, dd = _jitter(o, 0.6, rng), _jitter(d, 0.6, rng)
            X.append([(oo[1] - lon0) * m_lon, (oo[0] - lat0) * 111320.0,
                      (dd[1] - lon0) * m_lon, (dd[0] - lat0) * 111320.0])
            truth.append(g)
            origins.append(oo)

    start = time.perf_counter()
    labels = DBSCAN(eps=1500.0, min_samples=2).fit_predict(X)
    elapsed_ms = (time.perf_counter() - start) * 1000
    base = [hash((round(o[0] / 0.05), round(o[1] / 0.05))) for o in origins]

    def _sil(lbl):
        return round(float(silhouette_score(X, lbl)), 3) if 1 < len(set(lbl)) < len(X) else 0.0

    return {
        'n_samples': len(X),
        'model': {'silhouette': _sil(labels), 'ari': round(adjusted_rand_score(truth, labels), 3),
                  'n_clusters': len(set(labels) - {-1})},
        'baseline': {'silhouette': _sil(base), 'ari': round(adjusted_rand_score(truth, base), 3),
                     'n_clusters': len(set(base))},
        'latency_ms': round(elapsed_ms, 2),
    }


def full_report() -> Dict:
    return {'matching': evaluate_matcher(), 'clustering': evaluate_clustering()}
