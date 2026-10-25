"""Optional LightGBM inference with explicit unavailable/error states."""

import os
import time

FEATURE_NAMES = (
    "mean_speed_kmh",
    "max_speed_kmh",
    "speed_std_kmh",
    "mean_acceleration_mps2",
    "stop_ratio",
    "mean_accuracy_m",
    "point_count",
)
MIN_CLASSIFICATION_CONFIDENCE = 0.6


def extract_features(points):
    """Extract deterministic features from a sequence of validated GPS samples."""
    from .gps_service import haversine_km, validate_coordinate

    ordered = sorted(
        points,
        key=lambda point: point.get("sequence", point["timestamp"]),
    )
    if len(ordered) < 3:
        raise ValueError("Au moins trois points GPS sont nécessaires à l'analyse.")
    speeds = []
    accelerations = []
    accuracies = []
    previous_speed_mps = None
    for first, second in zip(ordered, ordered[1:]):
        start = first["timestamp"]
        end = second["timestamp"]
        seconds = (end - start).total_seconds()
        if seconds <= 0:
            raise ValueError("Les horodatages GPS doivent être strictement croissants.")
        start_coords = validate_coordinate(first["latitude"], first["longitude"])
        end_coords = validate_coordinate(second["latitude"], second["longitude"])
        speed_mps = haversine_km(start_coords, end_coords) * 1000 / seconds
        speeds.append(speed_mps * 3.6)
        if previous_speed_mps is not None:
            accelerations.append((speed_mps - previous_speed_mps) / seconds)
        previous_speed_mps = speed_mps
    accuracies = [max(0.0, float(point.get("accuracy_m", 0))) for point in ordered]
    mean_speed = sum(speeds) / len(speeds)
    return {
        "mean_speed_kmh": mean_speed,
        "max_speed_kmh": max(speeds),
        "speed_std_kmh": (
            sum((speed - mean_speed) ** 2 for speed in speeds) / len(speeds)
        ) ** 0.5,
        "mean_acceleration_mps2": (
            sum(abs(value) for value in accelerations) / len(accelerations)
            if accelerations else 0.0
        ),
        "stop_ratio": sum(speed < 1.0 for speed in speeds) / len(speeds),
        "mean_accuracy_m": sum(accuracies) / len(accuracies),
        "point_count": float(len(ordered)),
    }


def predict_transport(points):
    """Load a configured LightGBM model for inference, without heuristic fallback."""
    model_path = os.environ.get("TRANSPORT_MODEL_PATH", "")
    if not model_path or not os.path.isfile(model_path):
        return {"status": "unavailable", "mode": None, "confidence": None}
    try:
        import joblib
        import lightgbm
    except ImportError:
        return {"status": "unavailable", "mode": None, "confidence": None}
    try:
        features = extract_features(points)
        started = time.perf_counter()
        model = joblib.load(model_path)
        if not isinstance(model, lightgbm.LGBMClassifier):
            raise ValueError("L'artefact configuré n'est pas un classifieur LightGBM.")
        values = [[features[name] for name in FEATURE_NAMES]]
        probabilities = model.predict_proba(values)[0]
        elapsed_ms = (time.perf_counter() - started) * 1000
        classes = list(model.classes_)
        index = max(range(len(probabilities)), key=probabilities.__getitem__)
        confidence = float(probabilities[index])
        if not classes:
            raise ValueError("Le modèle ne fournit pas de classes.")
        if confidence < MIN_CLASSIFICATION_CONFIDENCE:
            return {
                "status": "low_confidence",
                "mode": None,
                "confidence": confidence,
                "inference_ms": elapsed_ms,
                "model_engine": f"LightGBM {lightgbm.__version__}",
                "features": features,
            }
        return {
            "status": "complete",
            "mode": str(classes[index]),
            "confidence": confidence,
            "inference_ms": elapsed_ms,
            "model_engine": f"LightGBM {lightgbm.__version__}",
            "features": features,
        }
    except Exception:
        import logging

        logging.getLogger(__name__).exception("LightGBM inference failed.")
        return {
            "status": "failed",
            "mode": None,
            "confidence": None,
        }
