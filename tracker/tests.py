import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
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
from tracker.services.multimodal_service import segment_points
from tracker.services.route_matching import (
    RouteServiceError,
    _request_json,
    match_osrm,
    query_overpass_context,
)
from tracker.services.transport_classifier import extract_features, predict_transport
from tracker.services.trip_service import add_point, finish_trip


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
            os.environ, {"GPS_ENCRYPTION_KEY": "a-secure-test-key-with-at-least-32-chars"}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

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
                    result = predict_transport(points)
                self.assertEqual(result["mode"], "car")
                self.assertEqual(result["status"], "complete")
                with patch(
                    "joblib.load", return_value=FakeModel([0.45, 0.55])
                ):
                    uncertain = predict_transport(points)
                self.assertEqual(uncertain["status"], "low_confidence")
                self.assertIsNone(uncertain["mode"])
                with patch(
                    "joblib.load", return_value=FakeModel([0.45, 0.55])
                ) as load:
                    load.side_effect = RuntimeError("test inference fault")
                    with self.assertLogs(
                        "tracker.services.transport_classifier", level="ERROR"
                    ):
                        failed = predict_transport(points)
                self.assertEqual(failed["status"], "failed")
                self.assertIsNone(failed["mode"])

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
            os.environ, {"GPS_ENCRYPTION_KEY": "a-secure-test-key-with-at-least-32-chars"}
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
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
