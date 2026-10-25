"""Tâches Celery (Beat) d'EcoPlanner."""
from celery import shared_task
from django.contrib.auth import get_user_model
from django.core.cache import cache

from .signals import refresh_budget
from .services.report import send_weekly_report
from .services.explain import explain_plan
from .services import planning

EXPLANATION_CACHE_KEY = 'planner:explanation:{}'
EXPLANATION_CACHE_TTL = 60 * 60 * 6  # 6 heures


@shared_task
def project_month_end_all():
    """Recalcule la projection de fin de mois de chaque utilisateur actif et notifie les dépassements."""
    count = 0
    for user in get_user_model().objects.filter(is_active=True, trip_records__isnull=False).distinct():
        refresh_budget(user)
        count += 1
    return count


@shared_task
def send_weekly_reports():
    """Envoie le rapport PDF hebdomadaire par e-mail."""
    sent = 0
    for user in get_user_model().objects.filter(is_active=True).exclude(email=''):
        sent += bool(send_weekly_report(user))
    return sent


@shared_task
def send_weekly_report_for(user_id):
    user = get_user_model().objects.filter(pk=user_id).first()
    return bool(user and send_weekly_report(user))


@shared_task
def generate_explanation_async(user_id):
    """Génère l'explication LLM en arrière-plan et la met en cache (évite de bloquer la requête HTTP)."""
    user = get_user_model().objects.filter(pk=user_id).first()
    if not user:
        return
    try:
        plan = planning.optimize_week(user)
        explanations = explain_plan(plan)
        cache.set(EXPLANATION_CACHE_KEY.format(user_id), explanations, EXPLANATION_CACHE_TTL)
        return explanations.get('source', 'template')
    except Exception:
        return 'error'
