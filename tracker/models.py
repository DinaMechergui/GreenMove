"""Eco-Tracker : modèle Trip MINIMAL.

Ce modèle est un socle volontairement réduit, écrit par Yathreb pour que EcoPlanner, l'audit GPS
et le RGPD puissent fonctionner. Lors du merge avec la branche de Roua (Mobility Tracker), conserver
le modèle de Roua et ajuster uniquement `planner/adapters.py` (mapping des champs) ; les autres
modules n'utilisent que : user, started_at, mode, distance_km, duration_min, co2_kg, gps_points.
"""
from django.conf import settings
from django.db import models


class Trip(models.Model):
    MODES = [('WALK', 'Marche'), ('BIKE', 'Vélo'), ('BUS', 'Bus'), ('METRO', 'Métro / TGM'),
             ('CARPOOL', 'Covoiturage'), ('CAR', 'Voiture')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trips')
    started_at = models.DateTimeField()
    mode = models.CharField(max_length=10, choices=MODES)
    distance_km = models.FloatField()
    duration_min = models.FloatField(default=0)
    co2_kg = models.FloatField(default=0)
    # Points GPS [{"lat":..,"lon":..,"t":..}] (donnée sensible : accès audités, vidée à la suppression du compte)
    gps_points = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ('-started_at',)

    def __str__(self):
        return f"{self.user} {self.mode} {self.distance_km:.1f} km"
