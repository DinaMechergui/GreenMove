"""Adaptateur tracker -> planner. SEUL point de couplage avec le modèle Trip de Roua.

Au merge : si le Trip de Roua a d'autres noms de champs, ne modifier que `trip_to_record_fields`.
"""
from django.apps import apps
from django.db.models.signals import post_save, post_delete

MODE_MAPPING = {
    'walk': 'WALK',
    'bicycle': 'BIKE',
    'bus': 'BUS',
    'metro': 'METRO',
    'car': 'CAR',
}


def get_trip_model():
    try:
        return apps.get_model('tracker', 'Trip')
    except LookupError:
        return None


def trip_to_record_fields(trip):
    if trip.status != trip.Status.COMPLETED:
        return None
    mode = trip.confirmed_transport_mode or trip.detected_transport_mode
    planner_mode = MODE_MAPPING.get(mode)
    if planner_mode is None:
        return None
    return {
        'user': trip.user,
        'date': trip.start_time,
        'mode': planner_mode,
        'distance_km': float(trip.distance_km),
        'duration_min': trip.duration_seconds / 60,
    }


def sync_trip(sender, instance, created=False, **kwargs):
    from .models import TripRecord
    fields = trip_to_record_fields(instance)
    source_trip_id = str(instance.pk)
    record = TripRecord.objects.filter(source_trip_id=source_trip_id).first()
    if fields is None:
        if record is not None:
            record.delete()
        return
    if record is None:
        TripRecord.objects.create(source_trip_id=source_trip_id, **fields)
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
        for trip in Trip.objects.all().iterator():
            if str(trip.pk) in done:
                continue
            sync_trip(Trip, trip)
            n += 1
    return n
