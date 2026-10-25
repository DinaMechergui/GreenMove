"""Transactional trip recording and completion."""

import hashlib
import json
import math
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.utils import timezone

from carbon_service.services import calculate_trip_emissions
from tracker.models import GPSPoint, Trip

from .anticheat_service import inspect_points
from .gps_service import (
    GPSDataError,
    decrypt_coordinates,
    encrypt_coordinates,
    haversine_km,
    parse_timestamp,
    validate_coordinate,
)
from .transport_classifier import predict_transport


def start_trip(user, idempotency_key):
    trip, _ = Trip.objects.get_or_create(
        user=user,
        idempotency_key=idempotency_key,
        defaults={"start_time": timezone.now()},
    )
    return trip


def add_point(trip, payload):
    try:
        raw_sequence = payload["sequence"]
        if isinstance(raw_sequence, bool):
            raise ValueError
        sequence = int(raw_sequence)
        if str(sequence) != str(raw_sequence):
            raise ValueError
        if sequence < 0:
            raise ValueError
        latitude, longitude = validate_coordinate(
            payload["latitude"], payload["longitude"]
        )
        recorded_at = parse_timestamp(payload["recorded_at"])
        accuracy = payload.get("accuracy_m")
        accuracy = None if accuracy in (None, "") else float(accuracy)
        speed = payload.get("speed_mps")
        speed = None if speed in (None, "") else float(speed)
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, GPSDataError):
            raise
        raise GPSDataError("Les données du point GPS sont incomplètes.") from exc
    if trip.gps_points.count() >= 50000:
        raise GPSDataError("La limite de 50 000 points par trajet est atteinte.")
    if (accuracy is not None and (accuracy < 0 or accuracy > 10000)) or (
        speed is not None and (speed < 0 or speed > 150)
    ):
        raise GPSDataError("La précision ou la vitesse GPS est hors limites.")
    if (accuracy is not None and not math.isfinite(accuracy)) or (
        speed is not None and not math.isfinite(speed)
    ):
        raise GPSDataError("La précision ou la vitesse GPS doit être finie.")
    if recorded_at < trip.start_time - timedelta(minutes=5):
        raise GPSDataError("L'horodatage précède le début du trajet.")
    encrypted_latitude, encrypted_longitude = encrypt_coordinates(latitude, longitude)
    try:
        point, created = GPSPoint.objects.get_or_create(
            trip=trip,
            sequence=sequence,
            defaults={
                "latitude_ciphertext": encrypted_latitude,
                "longitude_ciphertext": encrypted_longitude,
                "recorded_at": recorded_at,
                "accuracy_m": accuracy,
                "speed_mps": speed,
            },
        )
    except IntegrityError as exc:
        raise GPSDataError("Ce point GPS existe déjà.") from exc
    if not created:
        existing = decrypt_coordinates(
            point.latitude_ciphertext, point.longitude_ciphertext
        )
        if existing != (latitude, longitude) or point.recorded_at != recorded_at:
            raise GPSDataError("Le numéro de séquence est déjà associé à un autre point.")
    return point, created


def _trip_samples(trip):
    samples = []
    for point in trip.gps_points.order_by("sequence"):
        latitude, longitude = decrypt_coordinates(
            point.latitude_ciphertext, point.longitude_ciphertext
        )
        samples.append(
            {
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": point.recorded_at,
                "accuracy_m": point.accuracy_m or 0,
                "sequence": point.sequence,
            }
        )
    return samples


def _points_digest(samples):
    normalized_samples = [
        [
            round(sample["latitude"], 7),
            round(sample["longitude"], 7),
            sample["timestamp"].isoformat(),
        ]
        for sample in samples
    ]
    return hashlib.sha256(
        json.dumps(normalized_samples, separators=(",", ":")).encode("utf-8")
    ).hexdigest() if samples else ""


@transaction.atomic
def create_imported_trip(user, title, samples):
    digest = _points_digest(samples)
    replayed = Trip.objects.filter(user=user, points_digest=digest).exists()
    trip = Trip.objects.create(
        user=user,
        idempotency_key=uuid.uuid4(),
        title=title[:120],
        start_time=samples[0]["timestamp"],
        end_time=samples[-1]["timestamp"],
        status=Trip.Status.COMPLETED,
        duration_seconds=max(
            0, int((samples[-1]["timestamp"] - samples[0]["timestamp"]).total_seconds())
        ),
        validation_status=(
            Trip.ValidationStatus.SUSPECT if replayed else Trip.ValidationStatus.PENDING
        ),
    )
    encrypted_points = []
    for sequence, sample in enumerate(samples):
        latitude_ciphertext, longitude_ciphertext = encrypt_coordinates(
            sample["latitude"], sample["longitude"]
        )
        encrypted_points.append(
            GPSPoint(
                trip=trip,
                sequence=sequence,
                latitude_ciphertext=latitude_ciphertext,
                longitude_ciphertext=longitude_ciphertext,
                recorded_at=sample["timestamp"],
            )
        )
    GPSPoint.objects.bulk_create(encrypted_points)
    distance = sum(
        haversine_km(
            (first["latitude"], first["longitude"]),
            (second["latitude"], second["longitude"]),
        )
        for first, second in zip(samples, samples[1:])
    )
    trip.distance_km = Decimal(str(round(distance, 3)))
    inspection = inspect_points(samples)
    flags = list(inspection["flags"])
    if replayed:
        flags.append("replayed_trace")
    trip.validation_status = (
        Trip.ValidationStatus.SUSPECT
        if replayed or inspection["status"] == "suspect"
        else Trip.ValidationStatus.VALID
    )
    trip.validation_flags = sorted(set(flags))
    trip.points_digest = "" if replayed else digest
    trip.save(update_fields=(
        "distance_km", "validation_status", "validation_flags", "points_digest",
        "updated_at"
    ))
    return trip


def refresh_confirmed_carbon(trip):
    """Recalculate completed-trip CO2 and its single user-confirmed segment."""
    if trip.status != Trip.Status.COMPLETED:
        return trip
    selected_mode = trip.confirmed_transport_mode or trip.detected_transport_mode
    trip.co2_kg = (
        calculate_trip_emissions(trip.distance_km, selected_mode)
        if selected_mode else Decimal("0")
    )
    trip.segments.all().delete()
    if selected_mode and trip.distance_km > 0:
        trip.segments.create(
            order=1,
            transport_mode=selected_mode,
            distance_km=trip.distance_km,
            duration_seconds=trip.duration_seconds,
            co2_kg=trip.co2_kg,
            confidence=(
                trip.prediction_confidence
                if selected_mode == trip.detected_transport_mode else None
            ),
        )
    trip.save(update_fields=("co2_kg", "updated_at"))
    return trip


@transaction.atomic
def finish_trip(trip):
    trip = Trip.objects.select_for_update().get(pk=trip.pk)
    if trip.status == Trip.Status.COMPLETED:
        return trip
    end_time = timezone.now()
    if end_time < trip.start_time:
        raise GPSDataError("La fin du trajet précède son début.")
    samples = _trip_samples(trip)
    distance = sum(
        haversine_km(
            (first["latitude"], first["longitude"]),
            (second["latitude"], second["longitude"]),
        )
        for first, second in zip(samples, samples[1:])
    )
    classifier = predict_transport(samples) if len(samples) >= 3 else {
        "status": "unavailable", "mode": None, "confidence": None
    }
    mode = classifier.get("mode")
    supported_modes = {choice for choice, _ in Trip.TransportMode.choices}
    if mode not in supported_modes:
        mode = None
        if classifier["status"] == "complete":
            classifier = {
                **classifier,
                "status": "low_confidence",
                "mode": None,
            }
    mode_for_checks = trip.confirmed_transport_mode or mode
    inspection = inspect_points(samples, mode_for_checks) if samples else {
        "status": "suspect", "flags": ["insufficient_points"]
    }
    digest = _points_digest(samples)
    replayed = bool(
        digest
        and Trip.objects.filter(user=trip.user, points_digest=digest)
        .exclude(pk=trip.pk)
        .exists()
    )
    flags = list(inspection["flags"])
    if replayed:
        flags.append("replayed_trace")
    trip.end_time = end_time
    trip.status = Trip.Status.COMPLETED
    trip.distance_km = Decimal(str(round(distance, 3)))
    trip.duration_seconds = max(0, int((end_time - trip.start_time).total_seconds()))
    trip.detected_transport_mode = mode or ""
    trip.prediction_status = classifier["status"]
    trip.prediction_confidence = classifier.get("confidence")
    trip.validation_status = (
        Trip.ValidationStatus.SUSPECT
        if replayed or inspection["status"] == "suspect"
        else Trip.ValidationStatus.VALID
    )
    trip.validation_flags = sorted(set(flags))
    trip.points_digest = "" if replayed else digest
    selected_mode = trip.confirmed_transport_mode or mode
    if selected_mode:
        proposed_segments = []
        if not trip.confirmed_transport_mode and classifier["status"] == "complete":
            from .multimodal_service import segment_points

            proposed_segments = segment_points(samples)
            proposed_segments = [
                segment for segment in proposed_segments
                if segment["transport_mode"] in supported_modes
            ]
        if not proposed_segments:
            proposed_segments = [
                {
                    "transport_mode": selected_mode,
                    "distance_km": trip.distance_km,
                    "duration_seconds": trip.duration_seconds,
                    "confidence": trip.prediction_confidence if selected_mode == mode else None,
                }
            ]
        for segment in proposed_segments:
            segment["distance_km"] = Decimal(str(segment["distance_km"])).quantize(
                Decimal("0.001")
            )
        allocated_before_last = sum(
            (segment["distance_km"] for segment in proposed_segments[:-1]),
            Decimal("0"),
        )
        if allocated_before_last > trip.distance_km:
            proposed_segments = [
                {
                    "transport_mode": selected_mode,
                    "distance_km": trip.distance_km,
                    "duration_seconds": trip.duration_seconds,
                    "confidence": trip.prediction_confidence if selected_mode == mode else None,
                }
            ]
            allocated_before_last = Decimal("0")
        proposed_segments[-1]["distance_km"] = trip.distance_km - allocated_before_last
        trip.segments.all().delete()
        for order, segment in enumerate(proposed_segments, start=1):
            segment["co2_kg"] = calculate_trip_emissions(
                segment["distance_km"], segment["transport_mode"]
            )
            trip.segments.create(
                order=order,
                transport_mode=segment["transport_mode"],
                distance_km=segment["distance_km"],
                duration_seconds=segment["duration_seconds"],
                co2_kg=segment["co2_kg"],
                confidence=segment.get("confidence"),
            )
        trip.co2_kg = sum(
            (segment.co2_kg for segment in trip.segments.all()), Decimal("0")
        )
    trip.save()
    return trip
