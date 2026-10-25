"""Modèles EcoPlanner : historique de déplacements, trajets récurrents et budget carbone.

Le module `tracker` (Roua) ne fournit pas encore de modèle Trip : EcoPlanner possède donc
son propre historique (`TripRecord`) ; un adaptateur pourra le synchroniser plus tard.
"""
from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class Mode(models.TextChoices):
    WALK = 'WALK', _('Marche')
    BIKE = 'BIKE', _('Vélo')
    BUS = 'BUS', _('Bus')
    METRO = 'METRO', _('Métro / TGM')
    CARPOOL = 'CARPOOL', _('Covoiturage')
    CAR = 'CAR', _('Voiture')


class TripRecord(models.Model):
    """Un déplacement effectué (source de l'analyse des habitudes)."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trip_records')
    date = models.DateTimeField()
    mode = models.CharField(max_length=10, choices=Mode.choices)
    distance_km = models.FloatField()
    duration_min = models.FloatField(default=0)
    co2_kg = models.FloatField(default=0, editable=False)
    source_trip_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        unique=True,
        editable=False,
        help_text=_("Identifiant du Trip du tracker synchronisé"),
    )

    class Meta:
        ordering = ('-date',)
        indexes = [models.Index(fields=['user', 'date'])]

    def save(self, *args, **kwargs):
        from .services.emissions import co2_kg
        self.co2_kg = co2_kg(self.mode, self.distance_km)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user} {self.mode} {self.distance_km:.1f} km"


class RecurringTrip(models.Model):
    """Trajet habituel de la semaine (cours, réunion, travail) à planifier."""
    WEEKDAYS = [(0, _('Lundi')), (1, _('Mardi')), (2, _('Mercredi')), (3, _('Jeudi')),
                (4, _('Vendredi')), (5, _('Samedi')), (6, _('Dimanche'))]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='recurring_trips')
    label = models.CharField(max_length=100)
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS)
    arrival_time = models.TimeField(help_text=_("Heure à laquelle vous devez être arrivé"))
    distance_km = models.FloatField()
    origin = models.CharField(max_length=150, blank=True)
    destination = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering = ('weekday', 'arrival_time')

    def __str__(self):
        return f"{self.label} ({self.get_weekday_display()})"


class CarbonBudget(models.Model):
    """Budget carbone mensuel (kg CO2) ; défaut = objectif de l'utilisateur."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='carbon_budgets')
    month = models.DateField(help_text=_("Premier jour du mois"))
    budget_kg = models.FloatField(default=60.0)
    alert_level = models.PositiveSmallIntegerField(default=0, editable=False,
                                                   help_text=_("0 aucune, 1 = 80 %, 2 = 100 % déjà notifié"))

    class Meta:
        unique_together = ('user', 'month')
        ordering = ('-month',)

    def __str__(self):
        return f"{self.user} {self.month:%Y-%m}: {self.budget_kg} kg"
