"""Optional LightGBM inference with explicit unavailable/error states."""

import os
import time
from functools import lru_cache
from pathlib import Path

from django.conf import settings

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


def model_artifact_configured():
    """Return whether a model artifact path is configured and points to a file."""
    model_path = (
        os.environ.get("TRANSPORT_MODEL_PATH") or settings.TRANSPORT_MODEL_PATH
    ).strip()
    return bool(model_path) and Path(model_path).is_file()


@lru_cache(maxsize=4)
def _load_model(model_path, modified_ns, file_size):
    import joblib
    import lightgbm

    artifact_stat = os.stat(model_path)
    if (artifact_stat.st_mtime_ns, artifact_stat.st_size) != (
        modified_ns,
        file_size,
    ):
        raise OSError("L'artefact LightGBM a changé pendant son chargement.")
    model = joblib.load(model_path)
    artifact_stat = os.stat(model_path)
    if (artifact_stat.st_mtime_ns, artifact_stat.st_size) != (
        modified_ns,
        file_size,
    ):
        raise OSError("L'artefact LightGBM a changé pendant son chargement.")
    if not isinstance(model, lightgbm.LGBMClassifier):
        raise ValueError("L'artefact configuré n'est pas un classifieur LightGBM.")
    if getattr(model, "n_features_in_", len(FEATURE_NAMES)) != len(FEATURE_NAMES):
        raise ValueError("Le modèle n'utilise pas les caractéristiques GPS attendues.")
    return model, lightgbm.__version__


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
    model_path = (
        os.environ.get("TRANSPORT_MODEL_PATH") or settings.TRANSPORT_MODEL_PATH
    ).strip()
    if not model_path:
        return {"status": "unavailable", "mode": None, "confidence": None}
    try:
        model_stat = os.stat(model_path)
        model, lightgbm_version = _load_model(
            os.path.realpath(model_path),
            model_stat.st_mtime_ns,
            model_stat.st_size,
        )
        features = extract_features(points)
        started = time.perf_counter()
        values = [[features[name] for name in FEATURE_NAMES]]
        probabilities = model.predict_proba(values)[0]
        elapsed_ms = (time.perf_counter() - started) * 1000
        classes = list(model.classes_)
        if len(classes) != len(probabilities) or not classes:
            raise ValueError("Les classes du modèle ne correspondent pas aux probabilités.")
        index = max(range(len(probabilities)), key=probabilities.__getitem__)
        confidence = float(probabilities[index])
        if confidence < MIN_CLASSIFICATION_CONFIDENCE:
            return {
                "status": "low_confidence",
                "mode": str(classes[index]),
                "confidence": confidence,
                "inference_ms": elapsed_ms,
                "model_engine": f"LightGBM {lightgbm_version}",
                "features": features,
            }
        return {
            "status": "complete",
            "mode": str(classes[index]),
            "confidence": confidence,
            "inference_ms": elapsed_ms,
            "model_engine": f"LightGBM {lightgbm_version}",
            "features": features,
        }
    except FileNotFoundError:
        return {"status": "unavailable", "mode": None, "confidence": None}
    except ImportError:
        return {"status": "unavailable", "mode": None, "confidence": None}
    except Exception:
        import logging

        logging.getLogger(__name__).exception("LightGBM inference failed.")
        return {
            "status": "failed",
            "mode": None,
            "confidence": None,
        }
