"""Signaux EcoPlanner : jauge de budget carbone en temps réel après chaque trajet."""
from django.core.cache import cache
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import CarbonBudget, TripRecord
from .services import planning

GAUGE_CACHE_KEY = 'planner:budget:{}'


def refresh_budget(user, notify=True):
    """Recalcule la jauge, la met en cache (temps réel) et notifie aux seuils 80 % / 100 %."""
    status = planning.carbon_budget_status(user)
    cache.set(GAUGE_CACHE_KEY.format(user.pk), status, 60 * 60 * 24)
    if not notify:
        return status
    start = timezone.localdate().replace(day=1)
    budget, _ = CarbonBudget.objects.get_or_create(
        user=user, month=start, defaults={'budget_kg': status['budget_kg']})
    pct = status['used_pct']
    level = 2 if pct >= 100 else 1 if pct >= 80 else 0
    if level > budget.alert_level:
        budget.alert_level = level
        budget.save(update_fields=['alert_level'])
        if user.email:
            send_mail(
                subject='GreenMove : budget carbone ' + ('dépassé' if level == 2 else 'bientôt atteint'),
                message=(f"Bonjour {user.first_name or user.username},\n\n"
                         f"Vous avez utilisé {status['used_kg']} kg sur {status['budget_kg']} kg ce mois-ci "
                         f"({pct} %). Projection fin de mois : {status['projected_kg']} kg.\n\n"
                         "Ouvrez EcoPlanner pour ajuster votre plan de la semaine."),
                from_email=None, recipient_list=[user.email], fail_silently=True,
            )
    return status


@receiver(post_save, sender=TripRecord)
def update_budget_gauge(sender, instance, created, **kwargs):
    if created:
        refresh_budget(instance.user)
