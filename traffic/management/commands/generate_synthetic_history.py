import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from traffic.context import hourly_precipitation, is_holiday
from traffic.models import MonitoringPoint, TrafficSnapshot
from traffic.synthetic import speeds, synthetic_congestion


class Command(BaseCommand):
    help = "Génère un historique de trafic synthétique (pluie et jours fériés réels)"

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=60)
        parser.add_argument('--step', type=int, default=15, help='pas en minutes')
        parser.add_argument('--reset', action='store_true', help="supprime l'historique synthétique existant")

    def handle(self, *args, **opts):
        days, step = opts['days'], opts['step']
        points = list(MonitoringPoint.objects.filter(is_active=True))
        if not points:
            self.stderr.write('Aucun point : lance seed_traffic_points.')
            return
        if opts['reset']:
            TrafficSnapshot.objects.filter(source='synthetic').delete()

        rain = hourly_precipitation(days)
        if not rain:
            self.stdout.write('Météo indisponible : pluie = 0 partout.')

        rng = random.Random(42)  # reproductible
        end = timezone.now().replace(second=0, microsecond=0)
        end -= timedelta(minutes=end.minute % step)
        t = end - timedelta(days=days)

        batch, total = [], 0
        while t <= end:
            local = timezone.localtime(t)
            mm = rain.get(local.strftime('%Y-%m-%dT%H:00'), 0.0) or 0.0
            hol = is_holiday(local.date())
            for p in points:
                c = synthetic_congestion(p.profile, local, mm, hol, rng)
                cur, free = speeds(p.profile, c)
                batch.append(TrafficSnapshot(
                    point=p, timestamp=t, current_speed=cur, free_flow_speed=free,
                    congestion=c, precipitation_mm=mm, is_holiday=hol, source='synthetic'))
            if len(batch) >= 5000:
                TrafficSnapshot.objects.bulk_create(batch)
                total += len(batch)
                batch = []
            t += timedelta(minutes=step)
        TrafficSnapshot.objects.bulk_create(batch)
        total += len(batch)
        self.stdout.write(self.style.SUCCESS(f'{total} snapshots générés sur {days} jours.'))