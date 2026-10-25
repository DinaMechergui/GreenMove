"""Adaptateur tracker -> planner. SEUL point de couplage avec le modèle Trip de Roua.

Au merge : si le Trip de Roua a d'autres noms de champs, ne modifier que `trip_to_record_fields`.
"""
from django.apps import apps
from django.db.models.signals import post_save, post_delete
from django.utils import timezone


def get_trip_model():
    try:
        return apps.get_model('tracker', 'Trip')
    except LookupError:
        return None


def trip_to_record_fields(trip):
    return {
        'user': trip.user, 'date': trip.started_at, 'mode': trip.mode,
        'distance_km': trip.distance_km, 'duration_min': getattr(trip, 'duration_min', 0) or 0,
    }


def sync_trip(sender, instance, created=False, **kwargs):
    from .models import TripRecord
    fields = trip_to_record_fields(instance)
    record = TripRecord.objects.filter(source_trip_id=instance.pk).first()
    if record is None:
        TripRecord.objects.create(source_trip_id=instance.pk, **fields)  # déclenche le signal budget
    else:
        for k, v in fields.items():
            setattr(record, k, v)
        record.save()


def unsync_trip(sender, instance, **kwargs):
    from .models import TripRecord
    TripRecord.objects.filter(source_trip_id=instance.pk).delete()


def connect():
    Trip = get_trip_model()
    if Trip is not None:
        post_save.connect(sync_trip, sender=Trip, dispatch_uid='planner_sync_trip')
        post_delete.connect(unsync_trip, sender=Trip, dispatch_uid='planner_unsync_trip')


def backfill():
    """Importe les Trip existants non encore synchronisés (utile après le merge)."""
    Trip = get_trip_model()
    n = 0
    if Trip is not None:
        from .models import TripRecord
        done = set(TripRecord.objects.exclude(source_trip_id=None).values_list('source_trip_id', flat=True))
        for trip in Trip.objects.exclude(pk__in=done):
            sync_trip(Trip, trip)
            n += 1
    return n
