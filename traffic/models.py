from django.db import models
from django.utils import timezone


class MonitoringPoint(models.Model):
    PROFILES = [
        ('am_heavy', 'Plus chargé le matin (vers le centre)'),
        ('pm_heavy', 'Plus chargé le soir (sortie des bureaux)'),
        ('center', 'Centre-ville (matin, midi, soir)'),
        ('highway', 'Autoroute / axe majeur'),
    ]
    name = models.CharField(max_length=100, unique=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    profile = models.CharField(max_length=20, choices=PROFILES, default='am_heavy')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TrafficSnapshot(models.Model):
    SOURCES = [('tomtom', 'TomTom'), ('synthetic', 'Synthétique')]

    point = models.ForeignKey(MonitoringPoint, on_delete=models.CASCADE, related_name='snapshots')
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    current_speed = models.FloatField()    # km/h
    free_flow_speed = models.FloatField()  # km/h
    congestion = models.FloatField()       # 0 = fluide, 1 = bloqué
    precipitation_mm = models.FloatField(default=0)
    is_holiday = models.BooleanField(default=False)
    source = models.CharField(max_length=10, choices=SOURCES, default='synthetic')

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['point', '-timestamp'])]

    def __str__(self):
        return f'{self.point.name} @ {self.timestamp:%Y-%m-%d %H:%M} ({self.congestion:.2f})'