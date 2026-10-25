"""Mode-change smoothing and segment arithmetic helpers."""

from decimal import Decimal

from carbon_service.services import calculate_segment_emissions
from .gps_service import haversine_km
from .transport_classifier import predict_transport


def segment_points(points, *, window_size=8, minimum_points=5, classifier=None):
    """Classify overlapping-free windows and merge short/noisy adjacent predictions.

    The classifier must return its explicit state and confidence. An unavailable
    model yields no artificial mode assignments.
    """
    if window_size < minimum_points or minimum_points < 2:
        raise ValueError("Paramètres de segmentation incohérents.")
    classify = classifier or predict_transport
    ordered = sorted(points, key=lambda point: point["timestamp"])
    step = window_size - 1
    starts = list(range(0, max(1, len(ordered) - 1), step))
    valid_starts = [
        index for index in starts
        if len(ordered[index:index + window_size]) >= minimum_points
    ]
    windows = [ordered[index:index + window_size] for index in valid_starts]
    if windows and len(ordered) - (valid_starts[-1] + len(windows[-1])) < minimum_points:
        windows[-1] = ordered[valid_starts[-1]:]
    raw_segments = []
    supported_modes = {"walk", "bicycle", "car", "bus", "metro", "train"}
    for window in windows:
        prediction = classify(window)
        mode = prediction.get("mode") if prediction.get("status") == "complete" else None
        if mode not in supported_modes:
            continue
        distance = sum(
            haversine_km(
                (first["latitude"], first["longitude"]),
                (second["latitude"], second["longitude"]),
            )
            for first, second in zip(window, window[1:])
        )
        segment = {
            "transport_mode": mode,
            "distance_km": Decimal(str(round(distance, 3))),
            "duration_seconds": max(
                0, int((window[-1]["timestamp"] - window[0]["timestamp"]).total_seconds())
            ),
            "co2_kg": calculate_segment_emissions(distance, mode),
            "confidence": prediction.get("confidence"),
            "first_timestamp": window[0]["timestamp"],
            "last_timestamp": window[-1]["timestamp"],
            "window_count": 1,
        }
        if raw_segments and raw_segments[-1]["transport_mode"] == mode:
            previous = raw_segments[-1]
            previous["distance_km"] += segment["distance_km"]
            previous["duration_seconds"] += segment["duration_seconds"]
            previous["co2_kg"] += segment["co2_kg"]
            previous["last_timestamp"] = segment["last_timestamp"]
            previous["window_count"] += 1
        else:
            raw_segments.append(segment)
    smoothed = []
    index = 0
    while index < len(raw_segments):
        if (
            0 < index < len(raw_segments) - 1
            and raw_segments[index]["window_count"] == 1
            and raw_segments[index - 1]["transport_mode"]
            == raw_segments[index + 1]["transport_mode"]
        ):
            previous = raw_segments[index - 1]
            noisy = raw_segments[index]
            following = raw_segments[index + 1]
            previous["distance_km"] += noisy["distance_km"] + following["distance_km"]
            previous["duration_seconds"] += (
                noisy["duration_seconds"] + following["duration_seconds"]
            )
            previous["co2_kg"] += noisy["co2_kg"] + following["co2_kg"]
            previous["last_timestamp"] = following["last_timestamp"]
            previous["window_count"] += noisy["window_count"] + following["window_count"]
            index += 2
            continue
        smoothed.append(raw_segments[index])
        index += 1
    return smoothed
