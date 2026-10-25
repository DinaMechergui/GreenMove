"""Service de métriques IA : qualité du clustering KMeans, statistiques de CO₂ vs moyenne nationale."""
from collections import Counter
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from ..models import TripRecord
from .planning import classify_user, user_features, _kmeans, _kmeans_py

# Moyenne CO₂ / km des voitures tunisiennes (ANME 2023)
NATIONAL_AVG_CO2_KM = 0.21  # kg CO₂/km
# Objectif Accord de Paris pour les transports en Tunisie (2030)
PARIS_TARGET_KG_MONTH = 35.0


def _silhouette_approx(points, labels, centers, k):
    """Silhouette score simplifié (sans scipy) : moyenne des (b-a)/max(a,b)."""
    if len(points) < 2 or k < 2:
        return None
    scores = []
    for i, (p, lbl) in enumerate(zip(points, labels)):
        same = [points[j] for j, l in enumerate(labels) if l == lbl and j != i]
        if not same:
            scores.append(0.0)
            continue
        a = sum(sum((x - y) ** 2 for x, y in zip(p, q)) ** 0.5 for q in same) / len(same)
        other_clusters = [c for ci, c in enumerate(centers) if ci != lbl]
        b = min(sum((x - y) ** 2 for x, y in zip(p, c)) ** 0.5 for c in other_clusters)
        scores.append((b - a) / max(a, b) if max(a, b) > 0 else 0.0)
    return round(sum(scores) / len(scores), 3) if scores else None


def clustering_metrics(population_limit=500):
    """Retourne les métriques de qualité du clustering KMeans sur la population active."""
    User = get_user_model()
    users = list(User.objects.filter(is_active=True)[:population_limit])
    features_list = [(u, user_features(u)) for u in users]
    valid = [(u, f) for u, f in features_list if f is not None]

    if len(valid) < 3:
        return {
            'status': 'insufficient_data',
            'n_users_with_data': len(valid),
            'message': 'Pas assez de données pour le clustering (min 3 utilisateurs avec historique).',
        }

    points = [f for _, f in valid]
    k = min(3, len(points))
    elbow = []
    stability = None
    baseline_silhouette = None
    try:
        from sklearn.cluster import KMeans
        from sklearn.metrics import adjusted_rand_score, silhouette_score
        model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(points)
        labels = list(model.labels_)
        centers = [list(c) for c in model.cluster_centers_]
        inertia = round(float(model.inertia_), 3)
        for candidate_k in range(1, min(6, len(points) - 1) + 1):
            fitted = KMeans(n_clusters=candidate_k, n_init=10, random_state=0).fit(points)
            elbow.append({'k': candidate_k, 'inertia': round(float(fitted.inertia_), 3)})
        seeded_labels = [KMeans(n_clusters=k, n_init=10, random_state=seed).fit_predict(points)
                         for seed in range(5)]
        pair_scores = [adjusted_rand_score(seeded_labels[i], seeded_labels[j])
                       for i in range(len(seeded_labels)) for j in range(i + 1, len(seeded_labels))]
        stability = round(sum(pair_scores) / len(pair_scores), 3) if pair_scores else None
        baseline_labels = [0 if p[0] >= 0.55 else 1 if p[1] >= 0.5 else 2 for p in points]
        if 1 < len(set(baseline_labels)) < len(points):
            baseline_silhouette = round(float(silhouette_score(points, baseline_labels)), 3)
        if 1 < len(set(labels)) < len(points):
            silhouette = round(float(silhouette_score(points, labels)), 3)
        else:
            silhouette = None
    except ImportError:
        labels, centers = _kmeans_py(points, k)
        inertia = None
        silhouette = _silhouette_approx(points, labels, centers, k)
        elbow = []

    distribution = dict(Counter(labels))

    # Nommage des clusters
    cluster_names = {}
    for ci, c in enumerate(centers):
        cluster_names[ci] = 'Conducteur' if c[0] >= 0.55 else 'Mobilité douce' if c[1] >= 0.5 else 'Mixte'

    return {
        'status': 'ok',
        'algorithm': 'KMeans',
        'n_clusters': k,
        'n_users_analysed': len(valid),
        'n_users_total': len(users),
        'inertia': inertia,
        'elbow': elbow,
        'stability_ari_5_seeds': stability,
        'silhouette_score': silhouette,
        'baseline': {
            'method': 'règles fixes (voiture ≥ 55 %, mobilité douce ≥ 50 %, sinon mixte)',
            'silhouette_score': baseline_silhouette,
            'silhouette_delta': round(silhouette - baseline_silhouette, 3)
                if silhouette is not None and baseline_silhouette is not None else None,
        },
        'silhouette_interpretation': (
            'Excellent (>0.7)' if silhouette and silhouette > 0.7 else
            'Bon (0.5–0.7)' if silhouette and silhouette > 0.5 else
            'Acceptable (0.25–0.5)' if silhouette and silhouette > 0.25 else
            'Faible (<0.25)'
        ) if silhouette is not None else 'N/A',
        'cluster_distribution': {cluster_names.get(k, f'Cluster {k}'): v for k, v in distribution.items()},
        'cluster_centers': [
            {'name': cluster_names.get(i, f'Cluster {i}'),
             'car_ratio': round(c[0], 2),
             'soft_ratio': round(c[1], 2),
             'weekly_km_norm': round(c[2], 2)}
            for i, c in enumerate(centers)
        ],
    }


def co2_statistics(user=None):
    """Statistiques CO₂ : comparaison avec la moyenne nationale et l'objectif Paris."""
    since_30 = timezone.now() - timedelta(days=30)
    qs = TripRecord.objects.filter(date__gte=since_30)
    if user:
        qs = qs.filter(user=user)

    agg = qs.aggregate(
        total_co2=Sum('co2_kg'),
        total_km=Sum('distance_km'),
        n_trips=Count('id'),
    )
    total_co2 = agg['total_co2'] or 0
    total_km = agg['total_km'] or 0

    # Baseline si tout était fait en voiture
    baseline_co2 = total_km * NATIONAL_AVG_CO2_KM
    savings_vs_national = round(baseline_co2 - total_co2, 2)
    savings_pct = round(savings_vs_national / baseline_co2 * 100, 1) if baseline_co2 > 0 else 0
    vs_paris = round(total_co2 - PARIS_TARGET_KG_MONTH, 2)

    # Répartition par mode
    by_mode = list(
        qs.values('mode').annotate(co2=Sum('co2_kg'), km=Sum('distance_km'), n=Count('id'))
        .order_by('-co2')
    )

    return {
        'period': '30 derniers jours',
        'total_co2_kg': round(total_co2, 2),
        'total_km': round(total_km, 1),
        'n_trips': agg['n_trips'] or 0,
        'national_baseline_kg': round(baseline_co2, 2),
        'savings_vs_car_kg': savings_vs_national,
        'savings_vs_car_pct': savings_pct,
        'paris_target_kg': PARIS_TARGET_KG_MONTH,
        'vs_paris_target_kg': vs_paris,
        'below_paris_target': vs_paris <= 0,
        'by_mode': [{'mode': r['mode'], 'co2_kg': round(r['co2'] or 0, 2),
                     'km': round(r['km'] or 0, 1), 'trips': r['n']} for r in by_mode],
    }


def eco_leaderboard(limit=10):
    """Classement des utilisateurs les plus éco du mois (CO₂ le plus bas, km le plus élevé)."""
    User = get_user_model()
    since_30 = timezone.now() - timedelta(days=30)
    rows = (
        TripRecord.objects.filter(date__gte=since_30)
        .values('user__id', 'user__username', 'user__first_name', 'user__last_name')
        .annotate(co2=Sum('co2_kg'), km=Sum('distance_km'), trips=Count('id'))
        .order_by('co2')[:limit]
    )
    return [
        {
            'rank': i + 1,
            'user_id': r['user__id'],
            'username': r['user__username'],
            'display_name': f"{r['user__first_name']} {r['user__last_name']}".strip() or r['user__username'],
            'co2_kg': round(r['co2'] or 0, 2),
            'km': round(r['km'] or 0, 1),
            'trips': r['trips'],
            'eco_score': round(max(0, 100 - (r['co2'] or 0) * 2), 1),
        }
        for i, r in enumerate(rows)
    ]
