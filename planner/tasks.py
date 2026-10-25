"""Tâches Celery (Beat) d'EcoPlanner."""
from celery import shared_task
from django.contrib.auth import get_user_model

from .signals import refresh_budget
from .services.report import send_weekly_report


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
