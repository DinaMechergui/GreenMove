"""Load labeled Geolife trajectories into leakage-resistant LightGBM samples."""

import csv
from bisect import bisect_left, bisect_right
from datetime import datetime, timedelta
from pathlib import Path

from .gps_service import validate_coordinate
from .transport_classifier import extract_features

LABEL_MODES = {
    "walk": "walk",
    "walking": "walk",
    "bike": "bicycle",
    "bicycling": "bicycle",
    "bus": "bus",
    "car": "car",
    "taxi": "car",
    "subway": "metro",
    "train": "train",
}
WINDOW_SIZE = 8
MINIMUM_WINDOW_POINTS = 5
MAX_CONTIGUOUS_GAP = timedelta(minutes=5)


def _parse_label_time(value):
    if not isinstance(value, str):
        raise ValueError("Un horodatage Geolife est manquant.")
    try:
        return datetime.strptime(value.strip(), "%Y/%m/%d %H:%M:%S")
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"Horodatage Geolife invalide : {value!r}.") from exc


def _read_labels(path):
    labels = []
    skipped_labels = 0
    with path.open(encoding="utf-8-sig", newline="") as label_file:
        reader = csv.DictReader(label_file, delimiter="\t")
        columns = {
            (name or "").strip().casefold(): name for name in (reader.fieldnames or ())
        }
        required = ("start time", "end time", "transportation mode")
        if any(name not in columns for name in required):
            raise ValueError(f"En-tête labels.txt invalide : {path}.")
        for row in reader:
            start = _parse_label_time(row[columns["start time"]])
            end = _parse_label_time(row[columns["end time"]])
            if end < start:
                raise ValueError(f"Intervalle de label inversé dans {path}.")
            label = (row[columns["transportation mode"]] or "").strip().casefold()
            mode = LABEL_MODES.get(label)
            if mode:
                labels.append((start, end, mode))
            else:
                skipped_labels += 1
    return labels, skipped_labels


def _read_trajectory(path):
    samples_by_timestamp = {}
    skipped_points = 0
    with path.open(encoding="utf-8", newline="") as trajectory_file:
        reader = csv.reader(trajectory_file)
        for _ in range(6):
            next(reader, None)
        for line_number, row in enumerate(reader, start=7):
            if len(row) < 7:
                skipped_points += 1
                continue
            try:
                latitude, longitude = validate_coordinate(row[0], row[1])
                timestamp = datetime.fromisoformat(f"{row[5]} {row[6]}")
            except (TypeError, ValueError):
                skipped_points += 1
                continue
            coordinates = samples_by_timestamp.setdefault(timestamp, [0.0, 0.0, 0])
            coordinates[0] += latitude
            coordinates[1] += longitude
            coordinates[2] += 1
    return (
        [
            {
                "latitude": latitude_sum / count,
                "longitude": longitude_sum / count,
                "timestamp": timestamp,
                "accuracy_m": 0.0,
                "trajectory_id": path.name,
            }
            for timestamp, (latitude_sum, longitude_sum, count) in sorted(
                samples_by_timestamp.items()
            )
        ],
        skipped_points,
    )


def load_labeled_windows(geolife_root):
    """Return feature rows, modes, user groups, and skipped-label counts."""
    root = Path(geolife_root)
    data_root = root / "Data" if (root / "Data").is_dir() else root
    feature_rows = []
    labels = []
    groups = []
    skipped_labels = 0
    skipped_points = 0
    if not data_root.is_dir():
        raise ValueError(f"Répertoire de données Geolife introuvable : {data_root}.")
    user_directories = sorted(path for path in data_root.iterdir() if path.is_dir())
    for user_directory in user_directories:
        labels_path = user_directory / "labels.txt"
        trajectory_directory = user_directory / "Trajectory"
        if not labels_path.is_file() or not trajectory_directory.is_dir():
            continue
        user_labels, skipped = _read_labels(labels_path)
        skipped_labels += skipped
        trajectory_paths = sorted(trajectory_directory.glob("*.plt"))
        user_samples = []
        for path in trajectory_paths:
            samples, skipped = _read_trajectory(path)
            user_samples.extend(samples)
            skipped_points += skipped
        user_samples.sort(key=lambda sample: sample["timestamp"])
        timestamps = [sample["timestamp"] for sample in user_samples]
        for start, end, mode in user_labels:
            left = bisect_left(timestamps, start)
            right = bisect_right(timestamps, end)
            interval = user_samples[left:right]
            chunks = []
            for sample in interval:
                previous = chunks[-1][-1] if chunks else None
                if previous is not None and (
                    sample["trajectory_id"] != previous["trajectory_id"]
                    or not (
                        timedelta(0)
                        < sample["timestamp"] - previous["timestamp"]
                        <= MAX_CONTIGUOUS_GAP
                    )
                ):
                    chunks.append([])
                if not chunks:
                    chunks.append([])
                chunks[-1].append(sample)
            for chunk in chunks:
                for offset in range(0, len(chunk), WINDOW_SIZE - 1):
                    window = chunk[offset:offset + WINDOW_SIZE]
                    if len(window) < MINIMUM_WINDOW_POINTS:
                        continue
                    feature_rows.append(extract_features(window))
                    labels.append(mode)
                    groups.append(user_directory.name)
    if not feature_rows:
        raise ValueError(
            "Aucun échantillon Geolife annoté exploitable. Vérifiez labels.txt "
            "et les fichiers Trajectory/*.plt."
        )
    return feature_rows, labels, groups, skipped_labels, skipped_points
