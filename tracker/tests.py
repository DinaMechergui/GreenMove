import json
from io import BytesIO, StringIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from urllib.error import HTTPError
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from accounts.models import AuditLog
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from lightgbm import LGBMClassifier
from rest_framework.test import APIClient

from carbon_service.services import (
    calculate_alternative_emissions,
    calculate_carbon_savings,
    calculate_segment_emissions,
    calculate_segments_total,
    calculate_trip_emissions,
    get_emission_factor,
)
from planner.models import TripRecord
from tracker.models import GPSPoint, Trip, TripSegment
from tracker.services.anticheat_service import inspect_points
from tracker.services.gps_service import (
    GPSDataError,
    GPSKeyUnavailable,
    decrypt_coordinates,
    encrypt_coordinates,
    haversine_km,
    parse_timestamp,
    trip_points_with_coordinates,
    validate_coordinate,
)
from tracker.services.gpx_service import build_gpx, parse_gpx
from tracker.services.geolife_training import load_labeled_windows
from tracker.services.multimodal_service import segment_points
from tracker.services.route_matching import (
    RouteServiceError,
    _request_json,
    match_osrm,
    query_overpass_context,
)
from tracker.services.transport_classifier import (
    _load_model,
    extract_features,
    model_artifact_configured,
    predict_transport,
)
from tracker.services.trip_service import add_point, finish_trip

CONFIGURED_TRANSPORT_MODEL_PATH = os.environ.get("TRANSPORT_MODEL_PATH", "")

class CarbonServiceTests(TestCase):
    def test_factors_and_trip_calculation(self):
        self.assertEqual(get_emission_factor("walking"), 0)
        self.assertEqual(calculate_trip_emissions("10", "car"), Decimal("1.70"))
        self.assertEqual(calculate_alternative_emissions(10, "bicycle"), 0)

    def test_distance_validation_and_unknown_mode(self):
        for value in (-1, "not-a-number", float("nan")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                calculate_segment_emissions(value, "car")
        with self.assertRaises(ValueError):
            get_emission_factor("teleport")

    def test_savings_preserves_negative_and_mixed_modes(self):
        self.assertEqual(calculate_carbon_savings(1, 2), -1)
        self.assertEqual(
            calculate_segments_total(
                [
                    {"distance_km": 5, "transport_mode": "walk"},
                    {"distance_km": 2, "transport_mode": "car"},
                ]
            ),
            Decimal("0.34"),
        )
        with self.assertRaises(KeyError):
            calculate_segments_total([{"distance_km": 2}])


class GPSServiceTests(TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "GPS_ENCRYPTION_KEY": "a-secure-test-key-with-at-least-32-chars",
                "TRANSPORT_MODEL_PATH": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.model_setting = patch(
            "tracker.services.transport_classifier.settings.TRANSPORT_MODEL_PATH", ""
        )
        self.model_setting.start()
        self.addCleanup(self.model_setting.stop)

    def test_coordinate_validation_and_roundtrip_encryption(self):
        ciphertexts = encrypt_coordinates(36.8065, 10.1815)
        self.assertNotIn("36.8065", ciphertexts[0])
        self.assertEqual(decrypt_coordinates(*ciphertexts), (36.8065, 10.1815))
        with self.assertRaises(GPSDataError):
            validate_coordinate(91, 0)
        with self.assertRaises(GPSDataError):
            validate_coordinate(float("inf"), 0)

    def test_missing_key_is_an_explicit_error(self):
        with patch.dict(os.environ, {"GPS_ENCRYPTION_KEY": ""}):
            with self.assertRaises(GPSKeyUnavailable):
                encrypt_coordinates(0, 0)

    def test_timestamps_and_ciphertext_are_rejected_when_invalid(self):
        for value in (None, "not-a-date", "2026-10-24T10:00:00"):
            with self.subTest(value=value), self.assertRaises(GPSDataError):
                parse_timestamp(value)
        future = (timezone.now() + timedelta(minutes=10)).isoformat()
        with self.assertRaises(GPSDataError):
            parse_timestamp(future)
        with self.assertRaises(GPSDataError):
            decrypt_coordinates("invalid", "invalid")
        with self.assertRaises(GPSDataError):
            validate_coordinate("latitude", 0)

    def test_authorized_point_helper_decrypts_only_on_demand(self):
        user = get_user_model().objects.create_user(
            username="gps-owner", email="gps-owner@example.test"
        )
        trip = Trip.objects.create(user=user, idempotency_key=uuid.uuid4())
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        point = GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=timezone.now(),
        )
        result = list(trip_points_with_coordinates(trip))
        self.assertEqual((result[0].latitude, result[0].longitude), (36.8, 10.1))
        self.assertEqual(result[0].pk, point.pk)

    def test_haversine_distance(self):
        self.assertAlmostEqual(haversine_km((0, 0), (0, 1)), 111.195, places=2)


class GPXServiceTests(TestCase):
    def test_parse_and_export_valid_gpx(self):
        sample = (
            b'<gpx><trk><trkseg><trkpt lat="36.8" lon="10.1">'
            b'<time>2026-10-24T10:00:00Z</time></trkpt></trkseg></trk></gpx>'
        )
        points = parse_gpx(SimpleUploadedFile("track.gpx", sample))
        exported = build_gpx(points)
        self.assertIn(b"36.8000000", exported)
        self.assertIn(b"GreenMove", exported)

    def test_empty_malformed_and_entity_gpx_are_rejected(self):
        for content in (b"<gpx />", b"<gpx", b"<!DOCTYPE x [<!ENTITY e 'x'>]><gpx/>"):
            with self.subTest(content=content), self.assertRaises(GPSDataError):
                parse_gpx(SimpleUploadedFile("track.gpx", content))

    def test_oversized_gpx_and_non_gpx_root_are_rejected(self):
        with self.assertRaises(GPSDataError):
            parse_gpx(SimpleUploadedFile("large.gpx", b"x" * (2 * 1024 * 1024 + 1)))
        with self.assertRaises(GPSDataError):
            parse_gpx(SimpleUploadedFile("wrong.gpx", b"<root />"))


class AntiCheatAndAIServiceTests(TestCase):
    def setUp(self):
        self.start = timezone.now()
        self.environment = patch.dict(
            os.environ,
            {
                "GPS_ENCRYPTION_KEY": "a-secure-test-key-with-at-least-32-chars",
                "TRANSPORT_MODEL_PATH": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.model_setting = patch(
            "tracker.services.transport_classifier.settings.TRANSPORT_MODEL_PATH", ""
        )
        self.model_setting.start()
        self.addCleanup(self.model_setting.stop)
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="ai-test-user",
            email="ai-test-user@example.test",
            password="test-password",
        )
        self.client.force_login(self.user)

    def _point(self, lat, lon, seconds, accuracy=10):
        return {
            "latitude": lat,
            "longitude": lon,
            "timestamp": self.start + timedelta(seconds=seconds),
            "accuracy_m": accuracy,
        }

    def test_impossible_speed_is_flagged_but_low_accuracy_is_not(self):
        teleport = [
            self._point(36.8, 10.1, 0),
            self._point(37.8, 10.1, 1),
        ]
        self.assertIn("implausible_speed", inspect_points(teleport, "walk")["flags"])
        plausible = [
            self._point(36.8, 10.1, 0, 500),
            self._point(36.80001, 10.1, 60, 500),
        ]
        self.assertEqual(inspect_points(plausible, "walk")["status"], "valid")

    def test_anti_cheat_flags_invalid_accuracy_and_duplicate_timestamps(self):
        points = [
            self._point(36.8, 10.1, 0, -1),
            self._point(36.80001, 10.1, 0),
        ]
        result = inspect_points(points, "unrecognized-mode")
        self.assertEqual(result["status"], "suspect")
        self.assertIn("invalid_accuracy", result["flags"])
        self.assertIn("non_increasing_timestamp", result["flags"])
        self.assertIn(
            "insufficient_points",
            inspect_points([self._point(36.8, 10.1, 0)])["flags"],
        )

    def test_classifier_does_not_fake_a_prediction(self):
        self.assertEqual(
            predict_transport([]),
            {"status": "unavailable", "mode": None, "confidence": None},
        )
        with self.assertRaises(ValueError):
            extract_features([])

    def test_classifier_confidence_and_inference_failure_are_explicit(self):
        points = [
            self._point(36.8 + index * 0.0001, 10.1, index * 10)
            for index in range(4)
        ]

        class FakeModel(LGBMClassifier):
            classes_ = ["walk", "car"]

            def __init__(self, probabilities):
                self.probabilities = probabilities

            def predict_proba(self, _values):
                return [self.probabilities] if _values else []

        with TemporaryDirectory() as directory:
            model_path = Path(directory) / "model.joblib"
            model_path.write_bytes(b"test artifact")
            with patch.dict(os.environ, {"TRANSPORT_MODEL_PATH": str(model_path)}):
                with patch(
                    "joblib.load", return_value=FakeModel([0.1, 0.9])
                ):
                    _load_model.cache_clear()
                    result = predict_transport(points)
                self.assertEqual(result["mode"], "car")
                self.assertEqual(result["status"], "complete")
                with patch(
                    "joblib.load", return_value=FakeModel([0.45, 0.55])
                ):
                    _load_model.cache_clear()
                    uncertain = predict_transport(points)
                self.assertEqual(uncertain["status"], "low_confidence")
                self.assertEqual(uncertain["mode"], "car")
                with patch(
                    "joblib.load", return_value=FakeModel([0.45, 0.55])
                ) as load:
                    _load_model.cache_clear()
                    load.side_effect = RuntimeError("test inference fault")
                    with self.assertLogs(
                        "tracker.services.transport_classifier", level="ERROR"
                    ):
                        failed = predict_transport(points)
                self.assertEqual(failed["status"], "failed")
                self.assertIsNone(failed["mode"])
                _load_model.cache_clear()

    def test_reanalysis_runs_lightgbm_and_refreshes_segments_and_carbon(self):
        import joblib

        with TemporaryDirectory() as directory:
            model_path = Path(directory) / "transport.joblib"
            feature_rows = []
            labels = []
            modes = (
                ("walk", 4.0),
                ("bicycle", 16.0),
                ("car", 48.0),
                ("bus", 24.0),
            )
            for mode, speed in modes:
                for index in range(40):
                    offset = (index % 10) * 0.1
                    feature_rows.append(
                        [
                            speed + offset,
                            speed + 1 + offset,
                            0.3 + offset / 10,
                            0.05 + offset / 100,
                            0.05 if mode in {"car", "bicycle"} else 0.35,
                            10 + index % 3,
                            8,
                        ]
                    )
                    labels.append(mode)
            model = LGBMClassifier(
                n_estimators=60,
                num_leaves=7,
                min_child_samples=1,
                random_state=42,
                verbosity=-1,
            )
            model.fit(feature_rows, labels)
            joblib.dump(model, model_path)

            start_time = timezone.now() - timedelta(minutes=20)
            trip = Trip.objects.create(
                user=self.user,
                idempotency_key=uuid.uuid4(),
                start_time=start_time,
            )
            for sequence in range(20):
                add_point(
                    trip,
                    {
                        "sequence": sequence,
                        "latitude": 36.8 + sequence * 0.003,
                        "longitude": 10.1,
                        "recorded_at": (
                            start_time + timedelta(seconds=sequence * 30)
                        ).isoformat(),
                        "accuracy_m": 10,
                    },
                )
            trip = finish_trip(trip)
            self.assertEqual(trip.prediction_status, "unavailable")
            trip.segments.create(
                order=1,
                transport_mode="walk",
                distance_km=trip.distance_km,
                duration_seconds=trip.duration_seconds,
                co2_kg=0,
            )
            trip.co2_kg = Decimal("0")
            trip.save(update_fields=("co2_kg",))

            _load_model.cache_clear()
            with patch.dict(os.environ, {"TRANSPORT_MODEL_PATH": str(model_path)}):
                with patch("joblib.load", wraps=joblib.load) as load:
                    response = self.client.post(
                        reverse("tracker:retry-analysis", args=[trip.pk])
                    )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(load.call_count, 1)

            trip.refresh_from_db()
            self.assertEqual(trip.prediction_status, "complete")
            self.assertEqual(trip.detected_transport_mode, "car")
            self.assertGreater(trip.prediction_confidence, 0.6)
            self.assertGreater(trip.co2_kg, Decimal("0"))
            self.assertEqual(
                sum((segment.distance_km for segment in trip.segments.all()), Decimal("0")),
                trip.distance_km,
            )
            self.assertEqual(
                sum((segment.co2_kg for segment in trip.segments.all()), Decimal("0")),
                trip.co2_kg,
            )
            self.assertContains(
                self.client.get(reverse("tracker:detail", args=[trip.pk])),
                "Voiture",
            )
            _load_model.cache_clear()

    def test_geolife_loader_reads_labels_and_builds_features_without_training(self):
        with TemporaryDirectory() as directory:
            user_directory = Path(directory) / "Data" / "000"
            trajectory_directory = user_directory / "Trajectory"
            trajectory_directory.mkdir(parents=True)
            (user_directory / "labels.txt").write_text(
                "Start Time\tEnd Time\tTransportation Mode\n"
                "2008/10/23 00:00:00\t2008/10/23 00:04:00\twalk\n"
                "2008/10/23 00:00:00\t2008/10/23 00:04:00\tairplane\n",
                encoding="utf-8",
            )
            rows = [
                "Geolife trajectory", "WGS 84", "Altitude is in Feet",
                "Reserved 3", "0", "0",
            ]
            rows.extend(
                f"36.8{index:04d},10.1,0,0,0,2008-10-23,"
                f"00:0{index // 2}:{(index % 2) * 30:02d}"
                for index in range(8)
            )
            (trajectory_directory / "20081023.plt").write_text(
                "\n".join(rows), encoding="utf-8"
            )

            features, labels, groups, skipped, skipped_points = load_labeled_windows(
                directory
            )

        self.assertEqual(len(features), 1)
        self.assertEqual(labels, ["walk"])
        self.assertEqual(groups, ["000"])
        self.assertEqual(skipped, 1)
        self.assertEqual(skipped_points, 0)
        self.assertEqual(
            set(features[0]),
            {
                "mean_speed_kmh", "max_speed_kmh", "speed_std_kmh",
                "mean_acceleration_mps2", "stop_ratio", "mean_accuracy_m",
                "point_count",
            },
        )

    def test_geolife_loader_aggregates_duplicate_second_samples(self):
        with TemporaryDirectory() as directory:
            user_directory = Path(directory) / "Data" / "000"
            trajectory_directory = user_directory / "Trajectory"
            trajectory_directory.mkdir(parents=True)
            (user_directory / "labels.txt").write_text(
                "Start Time\tEnd Time\tTransportation Mode\n"
                "2008/10/23 00:00:00\t2008/10/23 00:04:00\twalk\n",
                encoding="utf-8",
            )
            rows = [
                "Geolife trajectory", "WGS 84", "Altitude is in Feet",
                "Reserved 3", "0", "0",
            ]
            rows.extend(
                f"{36.8 + index * 0.0001:.7f},10.1,0,0,0,2008-10-23,"
                f"00:00:{index // 2:02d}"
                for index in range(16)
            )
            rows.append("400.0,10.1,0,0,0,2008-10-23,00:00:08")
            (trajectory_directory / "20081023.plt").write_text(
                "\n".join(rows), encoding="utf-8"
            )

            features, labels, groups, _, skipped_points = load_labeled_windows(directory)

        self.assertTrue(features)
        self.assertEqual(set(labels), {"walk"})
        self.assertEqual(set(groups), {"000"})
        self.assertEqual(skipped_points, 1)

    def test_training_command_writes_model_and_metrics_for_synthetic_fixture(self):
        with TemporaryDirectory() as directory:
            data_root = Path(directory) / "Data"
            for user_index in range(4):
                user_directory = data_root / f"{user_index:03d}"
                trajectory_directory = user_directory / "Trajectory"
                trajectory_directory.mkdir(parents=True)
                labels = [
                    "Start Time\tEnd Time\tTransportation Mode",
                    "2008/10/23 00:00:00\t2008/10/23 00:04:00\twalk",
                    "2008/10/23 00:10:00\t2008/10/23 00:14:00\tcar",
                ]
                (user_directory / "labels.txt").write_text(
                    "\n".join(labels), encoding="utf-8"
                )
                for mode, start_minute, base_latitude, increment in (
                    ("walk", 0, 36.8 + user_index * 0.01, 0.00001),
                    ("car", 10, 36.8 + user_index * 0.01 + 0.1, 0.002),
                ):
                    rows = [
                        "Geolife trajectory", "WGS 84", "Altitude is in Feet",
                        "Reserved 3", "0", "0",
                    ]
                    rows.extend(
                        f"{base_latitude + index * increment:.7f},10.1,0,0,0,"
                        f"2008-10-23,00:{start_minute + index // 2:02d}:"
                        f"{(index % 2) * 30:02d}"
                        for index in range(8)
                    )
                    (trajectory_directory / f"{mode}.plt").write_text(
                        "\n".join(rows), encoding="utf-8"
                    )

            model_path = Path(directory) / "transport.joblib"
            call_command(
                "train_transport_model",
                data_dir=data_root,
                output=model_path,
                stdout=StringIO(),
            )
            metrics_path = model_path.with_suffix(".joblib.metrics.json")
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            self.assertTrue(model_path.is_file())

        self.assertEqual(
            metrics["split"],
            "GroupShuffleSplit by Geolife user, test_size=0.25",
        )
        self.assertGreater(metrics["train_samples"], 0)
        self.assertGreater(metrics["test_samples"], 0)
        self.assertEqual(metrics["train_users"] + metrics["test_users"], 4)
        self.assertEqual(set(metrics["confusion_matrix_labels"]), {"car", "walk"})
        self.assertEqual(
            metrics["inference_latency_ms"]["samples_measured"],
            metrics["test_samples"],
        )

    def test_short_noise_windows_are_not_assigned_a_mode(self):
        points = [self._point(36.8, 10.1, index) for index in range(4)]
        self.assertEqual(
            segment_points(
                points,
                window_size=8,
                minimum_points=5,
                classifier=lambda _: {"status": "complete", "mode": "walk"},
            ),
            [],
        )

    def test_multimodal_windows_merge_noise_and_keep_changes(self):
        points = [
            {
                "latitude": 36.8 + index * 0.0001,
                "longitude": 10.1,
                "timestamp": self.start + timedelta(seconds=index * 10),
            }
            for index in range(15)
        ]
        modes = iter(("walk", "bus"))
        segments = segment_points(
            points,
            classifier=lambda _: {
                "status": "complete", "mode": next(modes), "confidence": 0.9
            },
        )
        self.assertEqual([item["transport_mode"] for item in segments], ["walk", "bus"])
        expected_distance = sum(
            haversine_km(
                (first["latitude"], first["longitude"]),
                (second["latitude"], second["longitude"]),
            )
            for first, second in zip(points, points[1:])
        )
        self.assertAlmostEqual(
            sum(float(item["distance_km"]) for item in segments),
            round(expected_distance, 3),
            places=3,
        )
        merged = segment_points(
            points,
            classifier=lambda _: {
                "status": "complete", "mode": "walk", "confidence": 0.9
            },
        )
        self.assertEqual(len(merged), 1)

        noisy_modes = iter(("walk", "bus", "walk"))
        smoothed = segment_points(
            points + [
                {
                    "latitude": 36.8 + index * 0.0001,
                    "longitude": 10.1,
                    "timestamp": self.start + timedelta(seconds=index * 10),
                }
                for index in range(15, 22)
            ],
            classifier=lambda _: {
                "status": "complete", "mode": next(noisy_modes), "confidence": 0.7
            },
        )
        self.assertEqual([item["transport_mode"] for item in smoothed], ["walk"])

    @patch("tracker.services.route_matching._request_json")
    def test_osrm_response_and_failure_are_handled(self, request_json):
        request_json.return_value = {
            "code": "Ok",
            "matchings": [{"geometry": {"type": "LineString"}, "confidence": 0.8}],
            "tracepoints": [{}, None],
        }
        result = match_osrm([(36.8, 10.1), (36.81, 10.11)])
        self.assertEqual(result["unmatched_count"], 1)
        self.assertEqual(result["confidence"], 0.8)
        request_json.return_value = {"code": "NoMatch", "matchings": []}
        with self.assertRaises(RouteServiceError):
            match_osrm([(36.8, 10.1), (36.81, 10.11)])

    @patch("tracker.services.route_matching._request_json")
    def test_overpass_context_and_invalid_response(self, request_json):
        request_json.return_value = {"elements": [{"type": "way", "tags": {}}]}
        result = query_overpass_context([(36.8, 10.1), (36.81, 10.11)])
        self.assertEqual(result["feature_count"], 1)
        request_json.return_value = {"elements": None}
        with self.assertRaises(RouteServiceError):
            query_overpass_context([(36.8, 10.1)])

    @patch("tracker.services.route_matching.urlopen")
    def test_map_service_uses_user_agent_and_reports_no_matching_segment(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"{}"
        _request_json("https://example.invalid")
        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.get_header("User-agent"),
            "GreenMove-Mobility-Tracker/1.0",
        )

        urlopen.side_effect = HTTPError(
            "https://example.invalid",
            400,
            "Bad Request",
            {},
            BytesIO(b'{"code":"NoSegment","message":"no segment"}'),
        )
        with self.assertRaisesRegex(RouteServiceError, "aucun parcours exploitable"):
            _request_json("https://example.invalid")

    @patch("tracker.services.route_matching.urlopen", side_effect=TimeoutError)
    def test_external_route_timeout_is_explicit(self, _urlopen):
        with self.assertRaises(RouteServiceError):
            _request_json("https://example.invalid", timeout=0.01)
        _urlopen.assert_called_once()

    @patch("tracker.services.route_matching.urlopen")
    def test_route_invalid_json_and_oversized_responses_fail_closed(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b"not-json"
        with self.assertRaises(RouteServiceError):
            _request_json("https://example.invalid")
        response.read.return_value = b"x" * (2 * 1024 * 1024 + 1)
        with self.assertRaises(RouteServiceError):
            _request_json("https://example.invalid")
        with self.assertRaises(ValueError):
            match_osrm([(36.8, 10.1)], profile="unknown")


class TrackerViewsTests(TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "GPS_ENCRYPTION_KEY": "a-secure-test-key-with-at-least-32-chars",
                "TRANSPORT_MODEL_PATH": "",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.model_setting = patch(
            "tracker.services.transport_classifier.settings.TRANSPORT_MODEL_PATH", ""
        )
        self.model_setting.start()
        self.addCleanup(self.model_setting.stop)
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="citoyen", email="citoyen@example.test", password="password-safe-123"
        )
        self.other = user_model.objects.create_user(
            username="autre", email="autre@example.test", password="password-safe-123"
        )
        self.client.force_login(self.user)
        self.api_client = APIClient()
        self.api_client.force_authenticate(self.user)

    def test_dashboard_requires_authentication_and_shows_empty_state(self):
        self.client.logout()
        response = self.client.get(reverse("tracker:index"))
        self.assertEqual(response.status_code, 302)
        self.client.force_login(self.user)
        response = self.client.get(reverse("tracker:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucun trajet")

    def test_csrf_is_required_for_start_and_only_one_trip_can_be_active(self):
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        response = csrf_client.post(
            reverse("tracker:start"), {"idempotency_key": str(uuid.uuid4())}
        )
        self.assertEqual(response.status_code, 403)
        first_key = uuid.uuid4()
        self.client.post(
            reverse("tracker:start"), {"idempotency_key": str(first_key)}
        )
        self.client.post(
            reverse("tracker:start"), {"idempotency_key": str(uuid.uuid4())}
        )
        self.assertEqual(
            Trip.objects.filter(user=self.user, status=Trip.Status.RECORDING).count(),
            1,
        )

    def test_start_validation_invalid_json_and_payload_limit(self):
        response = self.client.post(reverse("tracker:start"), {"idempotency_key": "bad-key"})
        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        endpoint = reverse("tracker:record-point", args=[trip.pk])
        malformed = self.client.post(
            endpoint, data="{", content_type="application/json"
        )
        self.assertEqual(malformed.status_code, 400)
        oversized = self.client.post(
            endpoint, data=" " * 4097, content_type="application/json"
        )
        self.assertEqual(oversized.status_code, 413)

    def test_create_view_is_idempotent_and_point_payload_validates(self):
        key = uuid.uuid4()
        response = self.client.post(
            reverse("tracker:start"), {"idempotency_key": str(key)}
        )
        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.get(user=self.user, idempotency_key=key)
        endpoint = reverse("tracker:record-point", args=[trip.pk])
        now = timezone.now()
        payload = {
            "sequence": 0,
            "latitude": 36.8,
            "longitude": 10.1,
            "recorded_at": now.isoformat(),
            "accuracy_m": 10,
        }
        self.assertEqual(
            self.client.post(endpoint, data=json.dumps(payload), content_type="application/json").status_code,
            201,
        )
        duplicate = self.client.post(
            endpoint, data=json.dumps(payload), content_type="application/json"
        )
        self.assertEqual(duplicate.status_code, 200)
        self.assertTrue(duplicate.json()["duplicate"])
        payload["latitude"] = 200
        self.assertEqual(
            self.client.post(endpoint, data=json.dumps(payload), content_type="application/json").status_code,
            400,
        )

    def test_synthetic_gps_trace_persists_distance_and_accepts_weak_accuracy(self):
        start_time = timezone.now() - timedelta(minutes=5)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            start_time=start_time,
        )
        endpoint = reverse("tracker:record-point", args=[trip.pk])
        coordinates = [
            (36.8000, 10.1000),
            (36.8001, 10.1000),
            (36.8002, 10.1000),
            (36.8003, 10.1000),
        ]
        for sequence, (latitude, longitude) in enumerate(coordinates):
            response = self.client.post(
                endpoint,
                data=json.dumps(
                    {
                        "sequence": sequence,
                        "latitude": latitude,
                        "longitude": longitude,
                        "recorded_at": (
                            start_time + timedelta(seconds=sequence * 60)
                        ).isoformat(),
                        "accuracy_m": 122,
                    }
                ),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 201, response.content)
            self.assertTrue(response.json()["accepted"])

        self.assertEqual(GPSPoint.objects.filter(trip=trip).count(), 4)
        first_point = GPSPoint.objects.filter(trip=trip).order_by("sequence").first()
        self.assertNotIn("36.8000000", first_point.latitude_ciphertext)

        self.client.post(reverse("tracker:complete", args=[trip.pk]))
        trip.refresh_from_db()
        self.assertGreater(trip.distance_km, Decimal("0"))
        self.assertEqual(trip.prediction_status, "unavailable")
        self.assertNotIn("insufficient_points", trip.validation_flags)

    def test_missing_gps_key_is_reported_and_point_is_not_persisted(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        with patch.dict(os.environ, {"GPS_ENCRYPTION_KEY": ""}):
            response = self.client.post(
                reverse("tracker:record-point", args=[trip.pk]),
                data=json.dumps(
                    {
                        "sequence": 0,
                        "latitude": 36.8,
                        "longitude": 10.1,
                        "recorded_at": timezone.now().isoformat(),
                        "accuracy_m": 122,
                    }
                ),
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 503)
        self.assertIn("GPS_ENCRYPTION_KEY", response.json()["error"])
        self.assertFalse(GPSPoint.objects.filter(trip=trip).exists())

    def test_points_reject_non_increasing_timestamps_by_sequence(self):
        start_time = timezone.now() - timedelta(minutes=2)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            start_time=start_time,
        )
        endpoint = reverse("tracker:record-point", args=[trip.pk])
        first = {
            "sequence": 1,
            "latitude": 36.8001,
            "longitude": 10.1,
            "recorded_at": (start_time + timedelta(seconds=60)).isoformat(),
        }
        self.assertEqual(
            self.client.post(
                endpoint, data=json.dumps(first), content_type="application/json"
            ).status_code,
            201,
        )
        out_of_order = {
            **first,
            "sequence": 0,
            "recorded_at": (start_time + timedelta(seconds=90)).isoformat(),
        }
        response = self.client.post(
            endpoint,
            data=json.dumps(out_of_order),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("précéder", response.json()["error"])
        self.assertEqual(GPSPoint.objects.filter(trip=trip).count(), 1)

    def test_multimodal_trace_persists_walk_bus_walk_segments(self):
        start_time = timezone.now() - timedelta(minutes=30)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            start_time=start_time,
        )
        for sequence in range(42):
            add_point(
                trip,
                {
                    "sequence": sequence,
                    "latitude": 36.8 + sequence * 0.00001,
                    "longitude": 10.1,
                    "recorded_at": (
                        start_time + timedelta(seconds=sequence * 30)
                    ).isoformat(),
                    "accuracy_m": 10,
                },
            )
        predictions = iter(
            {"status": "complete", "mode": mode, "confidence": 0.9}
            for mode in ("walk", "walk", "bus", "bus", "walk", "walk")
        )
        with patch(
            "tracker.services.trip_service.predict_transport",
            return_value={"status": "complete", "mode": "walk", "confidence": 0.9},
        ), patch(
            "tracker.services.multimodal_service.predict_transport",
            side_effect=lambda _window: next(predictions),
        ):
            trip = finish_trip(trip)

        segments = list(trip.segments.all())
        self.assertEqual(
            [segment.transport_mode for segment in segments],
            ["walk", "bus", "walk"],
        )
        self.assertEqual(
            sum((segment.distance_km for segment in segments), Decimal("0")),
            trip.distance_km,
        )
        self.assertEqual(
            sum((segment.co2_kg for segment in segments), Decimal("0")),
            trip.co2_kg,
        )
        self.assertGreater(segments[1].distance_km, Decimal("0"))

    def test_export_is_disabled_without_points_and_endpoint_rejects_empty_trace(self):
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
        )
        detail = self.client.get(reverse("tracker:detail", args=[trip.pk]))
        self.assertContains(detail, 'aria-disabled="true"')
        self.assertNotContains(detail, f'href="{reverse("tracker:export-gpx", args=[trip.pk])}"')
        response = self.client.get(reverse("tracker:export-gpx", args=[trip.pk]))
        self.assertEqual(response.status_code, 400)
        self.assertIn("Aucun point GPS valide", response.content.decode())

    def test_detail_explains_missing_model_and_hides_impossible_retry(self):
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            prediction_status="unavailable",
        )
        with patch.dict(os.environ, {"TRANSPORT_MODEL_PATH": ""}):
            response = self.client.get(reverse("tracker:detail", args=[trip.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aucun modèle LightGBM entraîné")
        self.assertContains(response, "TRANSPORT_MODEL_PATH")
        self.assertNotContains(response, "Réessayer l'analyse")

    def test_low_confidence_retry_shows_candidate_without_assigning_carbon(self):
        start_time = timezone.now() - timedelta(minutes=10)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=start_time,
            end_time=timezone.now(),
            distance_km=Decimal("0.100"),
            duration_seconds=300,
            prediction_status="unavailable",
        )
        for sequence in range(8):
            latitude, longitude = encrypt_coordinates(
                36.8 + sequence * 0.00008, 10.1
            )
            GPSPoint.objects.create(
                trip=trip,
                sequence=sequence,
                latitude_ciphertext=latitude,
                longitude_ciphertext=longitude,
                recorded_at=start_time + timedelta(seconds=sequence * 30),
                accuracy_m=8,
            )

        with patch(
            "tracker.views.predict_transport",
            return_value={
                "status": "low_confidence",
                "mode": "walk",
                "confidence": 0.52,
            },
        ):
            retry = self.client.post(
                reverse("tracker:retry-analysis", args=[trip.pk])
            )

        self.assertEqual(retry.status_code, 302)
        trip.refresh_from_db()
        self.assertEqual(trip.prediction_status, "low_confidence")
        self.assertEqual(trip.detected_transport_mode, "walk")
        self.assertEqual(trip.co2_kg, Decimal("0"))
        self.assertFalse(trip.segments.exists())
        detail = self.client.get(reverse("tracker:detail", args=[trip.pk]))
        self.assertContains(detail, "Le modèle propose")
        self.assertContains(detail, "Piste IA · à confirmer 52 %")

    @skipUnless(
        CONFIGURED_TRANSPORT_MODEL_PATH,
        "Requires an explicitly configured trained LightGBM artifact.",
    )
    def test_configured_geolife_model_retries_and_renders_a_real_prediction(self):
        start_time = timezone.now() - timedelta(minutes=10)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=start_time,
            end_time=timezone.now(),
            distance_km=Decimal("0.100"),
            duration_seconds=300,
            prediction_status="unavailable",
        )
        for sequence in range(8):
            latitude, longitude = encrypt_coordinates(
                36.8 + sequence * 0.00008, 10.1
            )
            GPSPoint.objects.create(
                trip=trip,
                sequence=sequence,
                latitude_ciphertext=latitude,
                longitude_ciphertext=longitude,
                recorded_at=start_time + timedelta(seconds=sequence * 30),
                accuracy_m=8,
            )

        model_path = CONFIGURED_TRANSPORT_MODEL_PATH
        with patch.dict(os.environ, {"TRANSPORT_MODEL_PATH": model_path}):
            with patch(
                "tracker.services.transport_classifier.settings.TRANSPORT_MODEL_PATH",
                model_path,
            ):
                retry = self.client.post(
                    reverse("tracker:retry-analysis", args=[trip.pk])
                )

        self.assertEqual(retry.status_code, 302)
        trip.refresh_from_db()
        self.assertIn(trip.prediction_status, {"complete", "low_confidence"})
        self.assertIn(
            trip.detected_transport_mode,
            {mode for mode, _label in Trip.TransportMode.choices},
        )
        self.assertIsNotNone(trip.prediction_confidence)
        detail = self.client.get(reverse("tracker:detail", args=[trip.pk]))
        self.assertContains(detail, trip.get_detected_transport_mode_display())
        self.assertNotContains(detail, "Aucun modèle LightGBM entraîné")
        if trip.prediction_status == "low_confidence":
            self.assertFalse(trip.segments.exists())
            self.assertEqual(trip.co2_kg, Decimal("0"))
        else:
            self.assertTrue(trip.segments.exists())
            self.assertGreater(trip.co2_kg, Decimal("0"))

    def test_model_artifact_readiness_requires_a_real_file(self):
        with TemporaryDirectory() as directory:
            model_path = Path(directory) / "transport.joblib"
            with patch.dict(os.environ, {"TRANSPORT_MODEL_PATH": str(model_path)}):
                self.assertFalse(model_artifact_configured())
                model_path.write_bytes(b"temporary model artifact")
                self.assertTrue(model_artifact_configured())

    def test_owner_isolation_and_crud(self):
        trip = Trip.objects.create(user=self.other, idempotency_key=uuid.uuid4())
        self.assertEqual(
            self.client.get(reverse("tracker:detail", args=[trip.pk])).status_code, 404
        )
        owned = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        response = self.client.post(
            reverse("tracker:update", args=[owned.pk]),
            {"title": "Trajet domicile", "confirmed_transport_mode": "walk"},
        )
        self.assertEqual(response.status_code, 302)
        owned.refresh_from_db()
        self.assertEqual(owned.title, "Trajet domicile")
        self.assertEqual(
            self.client.post(reverse("tracker:delete", args=[owned.pk])).status_code, 302
        )
        self.assertFalse(Trip.objects.filter(pk=owned.pk).exists())

    def test_trip_detail_comparison_and_invalid_trip_are_owner_scoped(self):
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=timezone.now() - timedelta(minutes=2),
            end_time=timezone.now(),
            distance_km=Decimal("5.000"),
            confirmed_transport_mode="car",
            co2_kg=Decimal("0.85"),
        )
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=trip.start_time,
        )
        detail_response = self.client.get(reverse("tracker:detail", args=[trip.pk]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "36.8")
        comparison_response = self.client.get(reverse("tracker:compare", args=[trip.pk]))
        self.assertEqual(comparison_response.status_code, 200)
        self.assertContains(comparison_response, "distance identique")
        self.assertEqual(
            self.client.get(reverse("tracker:detail", args=[uuid.uuid4()])).status_code,
            404,
        )

    def test_retry_manifest_service_worker_and_offline_views(self):
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=timezone.now() - timedelta(minutes=1),
            end_time=timezone.now(),
        )
        retry_response = self.client.post(
            reverse("tracker:retry-analysis", args=[trip.pk])
        )
        self.assertEqual(retry_response.status_code, 302)
        trip.refresh_from_db()
        self.assertEqual(trip.prediction_status, "unavailable")
        self.assertEqual(self.client.get(reverse("tracker:manifest")).status_code, 200)
        worker_response = self.client.get(reverse("tracker:service-worker"))
        self.assertEqual(worker_response.status_code, 200)
        self.assertEqual(
            worker_response["Service-Worker-Allowed"], "/tracker/"
        )
        self.assertContains(worker_response, "greenmove-tracker-v3")
        self.assertEqual(self.client.get(reverse("tracker:offline")).status_code, 200)

    def test_gpx_import_export_and_private_export(self):
        contents = (
            b'<gpx><trk><trkseg><trkpt lat="36.8" lon="10.1">'
            b'<time>2026-10-24T10:00:00Z</time></trkpt>'
            b'<trkpt lat="36.8001" lon="10.1001">'
            b'<time>2026-10-24T10:01:00Z</time></trkpt></trkseg></trk></gpx>'
        )
        response = self.client.post(
            reverse("tracker:import-gpx"),
            {"file": SimpleUploadedFile("sample.gpx", contents)},
        )
        self.assertEqual(response.status_code, 302)
        trip = Trip.objects.get(user=self.user)
        export_response = self.client.get(reverse("tracker:export-gpx", args=[trip.pk]))
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(b"gpx", export_response.content)
        self.assertEqual(
            self.client.get(reverse("tracker:export-gpx", args=[uuid.uuid4()])).status_code,
            404,
        )
        self.assertEqual(GPSPoint.objects.filter(trip=trip).count(), 2)

    def test_gpx_import_rolls_back_if_encryption_key_is_missing(self):
        contents = (
            b'<gpx><trk><trkseg><trkpt lat="36.8" lon="10.1">'
            b'<time>2026-10-24T10:00:00Z</time></trkpt></trkseg></trk></gpx>'
        )
        with patch.dict(os.environ, {"GPS_ENCRYPTION_KEY": ""}):
            response = self.client.post(
                reverse("tracker:import-gpx"),
                {"file": SimpleUploadedFile("missing-key.gpx", contents)},
            )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Trip.objects.filter(user=self.user).exists())

    def test_gpx_invalid_upload_is_not_a_server_error(self):
        response = self.client.post(
            reverse("tracker:import-gpx"),
            {"file": SimpleUploadedFile("empty.gpx", b"<gpx />")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Trip.objects.filter(user=self.user).exists())

    def test_reimported_gpx_trace_is_marked_suspect(self):
        contents = (
            b'<gpx><trk><trkseg><trkpt lat="36.8" lon="10.1">'
            b'<time>2026-10-24T10:00:00Z</time></trkpt>'
            b'<trkpt lat="36.8001" lon="10.1">'
            b'<time>2026-10-24T10:01:00Z</time></trkpt></trkseg></trk></gpx>'
        )
        for _ in range(2):
            response = self.client.post(
                reverse("tracker:import-gpx"),
                {"file": SimpleUploadedFile("same.gpx", contents)},
            )
            self.assertEqual(response.status_code, 302)
        duplicate = Trip.objects.filter(user=self.user).order_by("-created_at").first()
        self.assertEqual(duplicate.validation_status, Trip.ValidationStatus.SUSPECT)
        self.assertIn("replayed_trace", duplicate.validation_flags)

    def test_gpx_form_rejects_unsupported_extension(self):
        response = self.client.post(
            reverse("tracker:import-gpx"),
            {"file": SimpleUploadedFile("route.txt", b"<gpx/>")},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ".gpx")

    def test_private_pages_report_missing_gps_key_without_exposing_data(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=timezone.now(),
        )
        with patch.dict(os.environ, {"GPS_ENCRYPTION_KEY": ""}):
            with self.assertLogs("tracker.views", level="ERROR"):
                heatmap_response = self.client.get(reverse("tracker:heatmap"))
            export_response = self.client.get(
                reverse("tracker:export-gpx", args=[trip.pk])
            )
        self.assertEqual(heatmap_response.status_code, 200)
        self.assertContains(heatmap_response, "clé GPS")
        self.assertEqual(export_response.status_code, 503)

    def test_trip_date_validation_and_completion(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        trip.end_time = trip.start_time - timedelta(seconds=1)
        with self.assertRaises(ValidationError):
            trip.full_clean()
        response = self.client.post(reverse("tracker:complete", args=[trip.pk]))
        self.assertEqual(response.status_code, 302)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.COMPLETED)

    def test_replayed_trace_is_flagged_and_segments_match_trip(self):
        start_time = timezone.now() - timedelta(minutes=1)
        coordinates = ((36.8, 10.1), (36.8001, 10.1))
        trips = []
        for _ in range(2):
            trip = Trip.objects.create(
                user=self.user,
                idempotency_key=uuid.uuid4(),
                start_time=start_time,
                confirmed_transport_mode="walk",
            )
            for sequence, (latitude, longitude) in enumerate(coordinates):
                add_point(
                    trip,
                    {
                        "sequence": sequence,
                        "latitude": latitude,
                        "longitude": longitude,
                        "recorded_at": (
                            start_time + timedelta(seconds=sequence * 20)
                        ).isoformat(),
                    },
                )
            finish_trip(trip)
            trips.append(trip)
        trips[0].refresh_from_db()
        trips[1].refresh_from_db()
        self.assertEqual(trips[1].validation_status, Trip.ValidationStatus.SUSPECT)
        self.assertIn("replayed_trace", trips[1].validation_flags)
        self.assertEqual(
            sum(segment.distance_km for segment in trips[0].segments.all()),
            trips[0].distance_km,
        )
        self.assertEqual(
            sum(segment.co2_kg for segment in trips[0].segments.all()),
            trips[0].co2_kg,
        )

    def test_trip_deletion_cascades_encrypted_points(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=timezone.now(),
        )
        trip.delete()
        self.assertEqual(GPSPoint.objects.count(), 0)
        self.assertEqual(TripSegment.objects.count(), 0)

    def test_heatmap_contains_only_the_authenticated_users_points(self):
        own_trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        other_trip = Trip.objects.create(user=self.other, idempotency_key=uuid.uuid4())
        for trip, latitude in ((own_trip, 36.8), (other_trip, 37.8)):
            encrypted_latitude, encrypted_longitude = encrypt_coordinates(latitude, 10.1)
            GPSPoint.objects.create(
                trip=trip,
                sequence=0,
                latitude_ciphertext=encrypted_latitude,
                longitude_ciphertext=encrypted_longitude,
                recorded_at=timezone.now(),
            )
        response = self.client.get(reverse("tracker:heatmap"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["heat_points"], [[36.8, 10.1]])
        self.assertNotContains(response, "37.8")

    def test_audited_gps_route_decrypts_points_and_blocks_other_users(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=timezone.now(),
        )
        url = reverse("tracker:trip_gps", args=[trip.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["points"][0]["latitude"],
            36.8,
        )
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditLog.Action.GPS_ACCESS, user=self.user
            ).exists()
        )
        other_client = self.client_class()
        other_client.force_login(self.other)
        self.assertEqual(other_client.get(url).status_code, 403)

    def test_account_anonymization_removes_tracker_gps_points(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        latitude, longitude = encrypt_coordinates(36.8, 10.1)
        GPSPoint.objects.create(
            trip=trip,
            sequence=0,
            latitude_ciphertext=latitude,
            longitude_ciphertext=longitude,
            recorded_at=timezone.now(),
        )
        from accounts.gdpr import delete_account

        delete_account(self.user)
        trip.refresh_from_db()
        self.assertEqual(GPSPoint.objects.filter(trip=trip).count(), 0)
        self.assertTrue(Trip.objects.filter(pk=trip.pk).exists())

    def test_planner_adapter_syncs_completed_tracker_trips_with_uuid_ids(self):
        start_time = timezone.now() - timedelta(minutes=3)
        trip = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=start_time,
            end_time=timezone.now(),
            duration_seconds=120,
            distance_km=Decimal("2.500"),
            confirmed_transport_mode="car",
        )
        record = TripRecord.objects.get(source_trip_id=str(trip.pk))
        self.assertEqual(record.mode, "CAR")
        self.assertEqual(record.distance_km, 2.5)
        self.assertEqual(record.duration_min, 2)
        trip.confirmed_transport_mode = "bus"
        trip.save(update_fields=("confirmed_transport_mode",))
        record.refresh_from_db()
        self.assertEqual(record.mode, "BUS")

    def test_invalid_date_filter_is_a_user_error_not_a_server_error(self):
        response = self.client.get(reverse("tracker:index"), {"from": "not-a-date"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "filtre")

    def test_drf_trip_crud_authentication_and_owner_permissions(self):
        endpoint = reverse("tracker:api-list")
        unauthenticated = APIClient().get(endpoint)
        self.assertEqual(unauthenticated.status_code, 401)
        response = self.api_client.post(
            endpoint,
            {
                "idempotency_key": str(uuid.uuid4()),
                "title": "Trajet API",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        trip_id = response.data["id"]
        self.assertEqual(response.data["title"], "Trajet API")
        self.assertNotIn("gps_points", response.data)
        self.assertEqual(self.api_client.get(endpoint).status_code, 200)

        completed = Trip.objects.create(
            user=self.user,
            idempotency_key=uuid.uuid4(),
            status=Trip.Status.COMPLETED,
            start_time=timezone.now() - timedelta(minutes=5),
            end_time=timezone.now(),
            distance_km=Decimal("5.000"),
        )
        detail = reverse("tracker:api-detail", args=[completed.pk])
        updated = self.api_client.patch(
            detail,
            {"title": "Corrigé", "confirmed_transport_mode": "car"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        completed.refresh_from_db()
        self.assertEqual(completed.co2_kg, Decimal("0.85"))
        self.assertEqual(completed.segments.count(), 1)

        other_client = APIClient()
        other_client.force_authenticate(self.other)
        self.assertEqual(other_client.get(detail).status_code, 404)
        self.assertEqual(self.api_client.delete(detail).status_code, 204)

    def test_drf_gps_point_and_completion_endpoints(self):
        trip = Trip.objects.create(user=self.user, idempotency_key=uuid.uuid4())
        point_url = reverse("tracker:api-point", args=[trip.pk])
        response = self.api_client.post(
            point_url,
            {
                "sequence": 0,
                "latitude": 36.8,
                "longitude": 10.1,
                "recorded_at": timezone.now().isoformat(),
                "accuracy_m": 10,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        completion = self.api_client.post(
            reverse("tracker:api-complete", args=[trip.pk]), {}, format="json"
        )
        self.assertEqual(completion.status_code, 200)
        trip.refresh_from_db()
        self.assertEqual(trip.status, Trip.Status.COMPLETED)
