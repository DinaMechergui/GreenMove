"""Train and evaluate the configured LightGBM transport classifier."""

import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path

import joblib
import lightgbm
from django.core.management.base import BaseCommand, CommandError
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    precision_recall_fscore_support,
)
from sklearn.model_selection import GroupShuffleSplit

from tracker.services.geolife_training import load_labeled_windows
from tracker.services.transport_classifier import FEATURE_NAMES


class Command(BaseCommand):
    help = "Entraîne et évalue LightGBM à partir du jeu Geolife annoté."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            required=True,
            type=Path,
            help="Répertoire Geolife contenant Data/<utilisateur>/labels.txt et Trajectory.",
        )
        parser.add_argument(
            "--output",
            type=Path,
            default=os.environ.get("TRANSPORT_MODEL_PATH") or None,
            help="Chemin de l'artefact .joblib (ou TRANSPORT_MODEL_PATH).",
        )

    def handle(self, *args, **options):
        output_path = options["output"]
        if output_path is None:
            raise CommandError("Indiquez --output ou configurez TRANSPORT_MODEL_PATH.")
        output_path = Path(output_path)
        try:
            (
                feature_rows,
                labels,
                groups,
                skipped_labels,
                skipped_points,
            ) = load_labeled_windows(options["data_dir"])
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        if len(set(groups)) < 2:
            raise CommandError(
                "Au moins deux utilisateurs annotés sont nécessaires au split "
                "train/test par utilisateur."
            )
        classes = sorted(set(labels))
        if len(classes) < 2:
            raise CommandError("Au moins deux modes de transport annotés sont nécessaires.")

        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
        train_indices, test_indices = next(
            splitter.split(feature_rows, labels, groups)
        )
        train_labels = [labels[index] for index in train_indices]
        test_labels = [labels[index] for index in test_indices]
        if len(set(train_labels)) < 2 or not test_labels:
            raise CommandError(
                "Le split par utilisateur ne contient pas assez de classes "
                "pour entraîner et évaluer le modèle."
            )

        def matrix(indices):
            return [
                [feature_rows[index][name] for name in FEATURE_NAMES]
                for index in indices
            ]

        model = lightgbm.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            num_leaves=15,
            class_weight="balanced",
            random_state=42,
            verbosity=-1,
        )
        model.fit(matrix(train_indices), train_labels)
        test_matrix = matrix(test_indices)
        predictions = model.predict(test_matrix)
        labels_ordered = [str(label) for label in model.classes_]
        precision, recall, f1, _ = precision_recall_fscore_support(
            test_labels,
            predictions,
            labels=labels_ordered,
            average="macro",
            zero_division=0,
        )
        latencies_ms = []
        for row in test_matrix[:1000]:
            started = time.perf_counter()
            model.predict_proba([row])
            latencies_ms.append((time.perf_counter() - started) * 1000)
        ordered_latencies = sorted(latencies_ms)
        report = classification_report(
            test_labels,
            predictions,
            labels=labels_ordered,
            output_dict=True,
            zero_division=0,
        )
        metrics = {
            "model_engine": f"LightGBM {lightgbm.__version__}",
            "features": list(FEATURE_NAMES),
            "random_state": 42,
            "split": "GroupShuffleSplit by Geolife user, test_size=0.25",
            "train_samples": len(train_indices),
            "test_samples": len(test_indices),
            "train_users": len({groups[index] for index in train_indices}),
            "test_users": len({groups[index] for index in test_indices}),
            "class_support": dict(Counter(test_labels)),
            "accuracy": float(accuracy_score(test_labels, predictions)),
            "macro_precision": float(precision),
            "macro_recall": float(recall),
            "macro_f1": float(f1),
            "classification_report": report,
            "confusion_matrix": confusion_matrix(
                test_labels, predictions, labels=labels_ordered
            ).tolist(),
            "confusion_matrix_labels": labels_ordered,
            "inference_latency_ms": {
                "samples_measured": len(latencies_ms),
                "p50": ordered_latencies[len(ordered_latencies) // 2],
                "p95": ordered_latencies[
                    min(len(ordered_latencies) - 1, int(len(ordered_latencies) * 0.95))
                ],
            },
            "unsupported_label_rows_skipped": skipped_labels,
            "invalid_gps_rows_skipped": skipped_points,
        }

        output_path = output_path.expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=f".{output_path.name}.",
                suffix=".tmp",
                dir=output_path.parent,
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
            joblib.dump(model, temporary_path)
            os.replace(temporary_path, output_path)
        except OSError as exc:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
            raise CommandError(f"Impossible d'écrire le modèle : {exc}") from exc

        metrics_path = output_path.with_suffix(output_path.suffix + ".metrics.json")
        try:
            metrics_path.write_text(
                json.dumps(metrics, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except OSError as exc:
            raise CommandError(
                f"Le modèle est enregistré, mais le rapport de métriques "
                f"n'a pas pu être écrit : {exc}"
            ) from exc
        self.stdout.write(self.style.SUCCESS(f"Modèle enregistré : {output_path}"))
        self.stdout.write(f"Métriques de test enregistrées : {metrics_path}")
        self.stdout.write(json.dumps(metrics, indent=2, ensure_ascii=False))
