from django.core.management.base import BaseCommand
from traffic.models import MonitoringPoint

POINTS = [
    ('Avenue Habib Bourguiba', 36.7992, 10.1800, 'center'),
    ('Avenue Mohamed V', 36.8100, 10.1840, 'center'),
    ('Montplaisir', 36.8210, 10.1830, 'center'),
    ('Charguia', 36.8420, 10.1910, 'center'),
    ('Lac 1', 36.8330, 10.2380, 'pm_heavy'),
    ('Lac 2', 36.8450, 10.2700, 'pm_heavy'),
    ('Ariana centre', 36.8665, 10.1647, 'am_heavy'),
    ('La Marsa', 36.8782, 10.3247, 'am_heavy'),
    ('Bardo', 36.8090, 10.1340, 'am_heavy'),
    ('Manouba', 36.8090, 10.0970, 'am_heavy'),
    ('Ben Arous', 36.7530, 10.2190, 'am_heavy'),
    ('Mourouj', 36.7370, 10.2120, 'am_heavy'),
    ('Autoroute A1 Mégrine', 36.7700, 10.2330, 'highway'),
    ('Pont de Radès', 36.7650, 10.2750, 'highway'),
    ('Autoroute A3 Manouba', 36.8000, 10.0800, 'highway'),
]


class Command(BaseCommand):
    help = 'Crée les points de surveillance du trafic'

    def handle(self, *args, **options):
        for name, lat, lon, profile in POINTS:
            _, created = MonitoringPoint.objects.update_or_create(
                name=name, defaults={'latitude': lat, 'longitude': lon, 'profile': profile})
            self.stdout.write(('créé : ' if created else 'mis à jour : ') + name)