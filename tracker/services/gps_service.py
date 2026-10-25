"""GPS validation, encryption, and distance calculations."""

import base64
import hashlib
import math
import os
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone


class GPSDataError(ValueError):
    """Raised when GPS input is invalid or cannot be safely decrypted."""


class GPSKeyUnavailable(RuntimeError):
    """Raised when the dedicated GPS encryption key is not configured."""


def _fernet() -> Fernet:
    secret = os.environ.get("GPS_ENCRYPTION_KEY", settings.GPS_ENCRYPTION_KEY)
    if len(secret) < 32:
        raise GPSKeyUnavailable(
            "GPS_ENCRYPTION_KEY doit contenir au moins 32 caractères."
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def validate_coordinate(latitude: object, longitude: object) -> tuple[float, float]:
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError) as exc:
        raise GPSDataError("Les coordonnées doivent être numériques.") from exc
    if not math.isfinite(lat) or not math.isfinite(lon):
        raise GPSDataError("Les coordonnées doivent être finies.")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise GPSDataError("Les coordonnées GPS sont hors limites.")
    return lat, lon


def encrypt_coordinate(value: float) -> str:
    return _fernet().encrypt(format(value, ".7f").encode("ascii")).decode("ascii")


def decrypt_coordinate(ciphertext: str) -> float:
    try:
        return float(_fernet().decrypt(ciphertext.encode("ascii")).decode("ascii"))
    except (InvalidToken, UnicodeError, ValueError) as exc:
        raise GPSDataError("Impossible de déchiffrer les coordonnées GPS.") from exc


def encrypt_coordinates(latitude: object, longitude: object) -> tuple[str, str]:
    lat, lon = validate_coordinate(latitude, longitude)
    return encrypt_coordinate(lat), encrypt_coordinate(lon)


def decrypt_coordinates(latitude_ciphertext: str, longitude_ciphertext: str) -> tuple[float, float]:
    return (
        decrypt_coordinate(latitude_ciphertext),
        decrypt_coordinate(longitude_ciphertext),
    )


def parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise GPSDataError("L'horodatage GPS est obligatoire.")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GPSDataError("L'horodatage GPS est invalide.") from exc
    if timezone.is_naive(timestamp):
        raise GPSDataError("L'horodatage GPS doit inclure son fuseau horaire.")
    if timestamp > timezone.now() + timedelta(minutes=5):
        raise GPSDataError("L'horodatage GPS ne peut pas être dans le futur.")
    return timestamp


def haversine_km(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, first)
    lat2, lon2 = map(math.radians, second)
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 6371.0088 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))


def trip_points_with_coordinates(trip):
    """Return owner-authorized point objects with decrypted coordinates."""
    for point in trip.gps_points.order_by("recorded_at", "sequence"):
        point.latitude, point.longitude = decrypt_coordinates(
            point.latitude_ciphertext, point.longitude_ciphertext
        )
        yield point
