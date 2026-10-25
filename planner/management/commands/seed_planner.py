"""Données de démonstration EcoPlanner : 8 semaines d'historique + trajets habituels."""
import random
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from planner.models import RecurringTrip, TripRecord


class Command(BaseCommand):
    help = "Crée un historique de déplacements et des trajets habituels pour un utilisateur (défaut : tous les comptes démo)."

    def add_arguments(self, parser):
        parser.add_argument('--username', help="Limiter à un utilisateur")

    def handle(self, *args, **opts):
        User = get_user_model()
        users = User.objects.filter(username=opts['username']) if opts['username'] else User.objects.filter(is_active=True)[:10]
        rng = random.Random(42)
        now = timezone.now()
        for user in users:
            if TripRecord.objects.filter(user=user).exists():
                continue
            for day in range(56):
                when = (now - timedelta(days=day)).replace(hour=rng.choice([8, 8, 9, 17, 18]), minute=rng.randint(0, 59))
                if when.weekday() >= 5 and rng.random() < 0.6:
                    continue
                mode = rng.choices(['CAR', 'BUS', 'METRO', 'BIKE', 'WALK', 'CARPOOL'], [5, 2, 2, 1, 1, 1])[0]
                km = round(rng.uniform(2, 15), 1)
                TripRecord.objects.create(user=user, date=when, mode=mode, distance_km=km, duration_min=km * 3)
            if not RecurringTrip.objects.filter(user=user).exists():
                for wd in range(5):
                    RecurringTrip.objects.create(user=user, label='Travail / Université', weekday=wd,
                                                 arrival_time=time(9, 0), distance_km=9.5)
            self.stdout.write(f"Planner : données de démo pour {user.username}")
