"""Tâches Celery de MobilityMatch (traitement IA asynchrone exigé par la grille)."""
import time

from celery import shared_task
from django.core.cache import cache

METRICS_CACHE_KEY = 'match:ai_metrics'
METRICS_STATUS_KEY = 'match:ai_metrics:status'
METRICS_TTL = 60 * 60 * 6  # 6 h


@shared_task
def evaluate_ai_async():
    """Calcule les métriques IA (matching + clustering) et les met en cache avec le temps mesuré."""
    from .services.metrics import full_report

    cache.set(METRICS_STATUS_KEY, 'running', METRICS_TTL)
    start = time.perf_counter()
    try:
        report = full_report()
        report['duration_s'] = round(time.perf_counter() - start, 2)
        cache.set(METRICS_CACHE_KEY, report, METRICS_TTL)
        cache.set(METRICS_STATUS_KEY, 'done', METRICS_TTL)
        return 'done'
    except Exception:
        cache.set(METRICS_STATUS_KEY, 'error', METRICS_TTL)
        return 'error'


@shared_task
def refresh_ride_groups():
    """Recalcule et persiste les groupes DBSCAN en arrière-plan (Celery Beat)."""
    from .services.clusters import compute_and_persist_groups
    return len(compute_and_persist_groups())
