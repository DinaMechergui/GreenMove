"""Explainable GPS plausibility checks; low accuracy alone is not suspicious."""

from .gps_service import haversine_km, validate_coordinate

MAX_SPEED_KMH = {
    "walk": 12,
    "bicycle": 70,
    "car": 220,
    "bus": 140,
    "metro": 160,
    "train": 320,
}


def inspect_points(points, transport_mode=None):
    """Return a review status and rule identifiers, without rejecting GPS noise."""
    ordered = sorted(
        points,
        key=lambda item: item.get("sequence", item["timestamp"]),
    )
    flags = []
    speed_limit = MAX_SPEED_KMH.get(transport_mode or "", 320)
    last_time = None
    last_coordinates = None
    for item in ordered:
        try:
            coordinates = validate_coordinate(item["latitude"], item["longitude"])
            timestamp = item["timestamp"]
            accuracy = float(item.get("accuracy_m", 0))
        except (KeyError, TypeError, ValueError):
            flags.append("invalid_point")
            continue
        if accuracy < 0:
            flags.append("invalid_accuracy")
        if last_time is not None:
            seconds = (timestamp - last_time).total_seconds()
            if seconds <= 0:
                flags.append("non_increasing_timestamp")
            elif last_coordinates is not None:
                distance = haversine_km(last_coordinates, coordinates)
                speed_kmh = distance / (seconds / 3600)
                if speed_kmh > speed_limit:
                    flags.append("implausible_speed")
        last_time = timestamp
        last_coordinates = coordinates
    if len(ordered) < 2:
        flags.append("insufficient_points")
    return {
        "status": "suspect" if any(flag != "insufficient_points" for flag in flags) else "valid",
        "flags": sorted(set(flags)),
    }
