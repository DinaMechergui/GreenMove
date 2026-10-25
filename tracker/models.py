"""Private mobility trips and encrypted location samples."""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Trip(models.Model):
    class Status(models.TextChoices):
        RECORDING = "recording", "En cours"
        COMPLETED = "completed", "Terminé"

    class TransportMode(models.TextChoices):
        WALK = "walk", "Marche"
        BICYCLE = "bicycle", "Vélo"
        CAR = "car", "Voiture"
        BUS = "bus", "Bus"
        METRO = "metro", "Métro / tram"
        TRAIN = "train", "Train"

    class ValidationStatus(models.TextChoices):
        PENDING = "pending", "À vérifier"
        VALID = "valid", "Valide"
        SUSPECT = "suspect", "À vérifier"
        REJECTED = "rejected", "Rejeté"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mobility_trips"
    )
    idempotency_key = models.UUIDField()
    title = models.CharField("Nom du trajet", max_length=120, blank=True)
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.RECORDING
    )
    distance_km = models.DecimalField(max_digits=9, decimal_places=3, default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    detected_transport_mode = models.CharField(
        max_length=12, choices=TransportMode.choices, blank=True
    )
    confirmed_transport_mode = models.CharField(
        max_length=12, choices=TransportMode.choices, blank=True
    )
    prediction_confidence = models.FloatField(null=True, blank=True)
    prediction_status = models.CharField(max_length=20, default="unavailable")
    co2_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    validation_status = models.CharField(
        max_length=10, choices=ValidationStatus.choices, default=ValidationStatus.PENDING
    )
    validation_flags = models.JSONField(default=list, blank=True)
    points_digest = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-start_time",)
        constraints = [
            models.UniqueConstraint(
                fields=("user", "idempotency_key"),
                name="tracker_trip_user_idempotency_unique",
            ),
            models.UniqueConstraint(
                fields=("user", "points_digest"),
                condition=~Q(points_digest=""),
                name="tracker_trip_user_points_digest_unique",
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=Q(status="recording"),
                name="tracker_one_active_trip_per_user",
            ),
        ]

    def clean(self):
        super().clean()
        if self.end_time and self.end_time < self.start_time:
            raise ValidationError({"end_time": "La fin doit être postérieure au début."})

    @property
    def duration_display(self):
        seconds = self.duration_seconds
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    def __str__(self):
        return self.title or f"Trajet du {self.start_time:%d/%m/%Y %H:%M}"


class GPSPoint(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="gps_points")
    sequence = models.PositiveIntegerField()
    latitude_ciphertext = models.CharField(max_length=255)
    longitude_ciphertext = models.CharField(max_length=255)
    recorded_at = models.DateTimeField()
    accuracy_m = models.FloatField(null=True, blank=True)
    speed_mps = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("recorded_at", "sequence")
        constraints = [
            models.UniqueConstraint(
                fields=("trip", "sequence"), name="tracker_point_trip_sequence_unique"
            )
        ]

    def __str__(self):
        return f"Point {self.sequence} du trajet {self.trip_id}"


class TripSegment(models.Model):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="segments")
    order = models.PositiveSmallIntegerField()
    transport_mode = models.CharField(max_length=12, choices=Trip.TransportMode.choices)
    distance_km = models.DecimalField(max_digits=9, decimal_places=3)
    duration_seconds = models.PositiveIntegerField(default=0)
    co2_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    confidence = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ("order",)
        constraints = [
            models.UniqueConstraint(
                fields=("trip", "order"), name="tracker_segment_trip_order_unique"
            )
        ]
