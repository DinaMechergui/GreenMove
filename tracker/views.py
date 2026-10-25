"""Authenticated server-rendered mobility tracker."""

import json
import logging
import uuid
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Case, CharField, Count, F, Sum, When
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST
from django.db import IntegrityError

from carbon_service.services import (
    calculate_alternative_emissions,
    calculate_carbon_savings,
)
from .forms import GPXUploadForm, TripUpdateForm
from .models import GPSPoint, Trip
from .services.gps_service import (
    GPSDataError,
    GPSKeyUnavailable,
    decrypt_coordinates,
)
from .services.gpx_service import build_gpx, parse_gpx
from .services.trip_service import (
    _replace_segments,
    add_point,
    create_imported_trip,
    finish_trip,
    refresh_confirmed_carbon,
    start_trip,
)
from .services.transport_classifier import model_artifact_configured, predict_transport
from .services.multimodal_service import segment_points

logger = logging.getLogger(__name__)


def _owned_trip(request, trip_id):
    return get_object_or_404(
        Trip.objects.prefetch_related("gps_points", "segments"),
        pk=trip_id,
        user=request.user,
    )


def _map_points(trip):
    result = []
    try:
        for point in trip.gps_points.order_by("sequence"):
            latitude, longitude = decrypt_coordinates(
                point.latitude_ciphertext, point.longitude_ciphertext
            )
            result.append(
                {
                    "sequence": point.sequence,
                    "latitude": latitude,
                    "longitude": longitude,
                    "recorded_at": point.recorded_at.isoformat(),
                }
            )
    except GPSKeyUnavailable:
        logger.error("GPS map unavailable: GPS_ENCRYPTION_KEY is not configured.")
    except GPSDataError:
        logger.error("GPS map unavailable: stored GPS ciphertext is invalid.")
    return result


@login_required
def index(request):
    all_trips = Trip.objects.filter(user=request.user)
    trips = all_trips
    search = request.GET.get("q", "").strip()
    if search:
        trips = trips.filter(title__icontains=search)
    transport = request.GET.get("transport", "")
    if transport in {value for value, _ in Trip.TransportMode.choices}:
        trips = trips.filter(confirmed_transport_mode=transport) | trips.filter(
            confirmed_transport_mode="", detected_transport_mode=transport
        )
    for parameter, lookup in (("from", "gte"), ("to", "lte")):
        value = request.GET.get(parameter, "")
        if value:
            try:
                filter_date = date.fromisoformat(value)
            except ValueError:
                messages.warning(request, f"Le filtre « {parameter} » est invalide.")
            else:
                trips = trips.filter(**{f"start_time__date__{lookup}": filter_date})
    page = Paginator(trips.distinct(), 20).get_page(request.GET.get("page"))
    query_parameters = request.GET.copy()
    query_parameters.pop("page", None)
    completed_trips = all_trips.filter(status=Trip.Status.COMPLETED)
    summary = completed_trips.aggregate(
        trip_count=Count("pk"),
        distance_km=Sum("distance_km"),
        duration_seconds=Sum("duration_seconds"),
        co2_kg=Sum("co2_kg"),
    )
    mode_counts = (
        completed_trips.annotate(
            display_mode=Case(
                When(confirmed_transport_mode="", then=F("detected_transport_mode")),
                default=F("confirmed_transport_mode"),
                output_field=CharField(),
            )
        )
        .exclude(display_mode="")
        .values("display_mode")
        .annotate(total=Count("pk"))
    )
    mode_count_map = {item["display_mode"]: item["total"] for item in mode_counts}
    mode_distribution = [
        {
            "value": mode,
            "label": label,
            "count": mode_count_map.get(mode, 0),
            "percentage": round(
                mode_count_map.get(mode, 0) * 100 / max(summary["trip_count"] or 0, 1)
            ),
        }
        for mode, label in Trip.TransportMode.choices
        if mode_count_map.get(mode, 0)
    ]
    recent_trips = all_trips.filter(status=Trip.Status.COMPLETED)[:5]
    active_trip = Trip.objects.filter(
        user=request.user, status=Trip.Status.RECORDING
    ).first()
    return render(
        request,
        "tracker/dashboard.html",
        {
            "page": page,
            "active_trip": active_trip,
            "transport_modes": Trip.TransportMode.choices,
            "idempotency_key": uuid.uuid4(),
            "summary": summary,
            "mode_distribution": mode_distribution,
            "recent_trips": recent_trips,
            "search": search,
            "pagination_query": query_parameters.urlencode(),
        },
    )


@login_required
@require_POST
def start(request):
    try:
        idempotency_key = uuid.UUID(request.POST["idempotency_key"])
    except (KeyError, ValueError, TypeError):
        messages.error(request, "Impossible de démarrer : identifiant de session invalide.")
        return redirect("tracker:index")
    if Trip.objects.filter(user=request.user, status=Trip.Status.RECORDING).exists():
        messages.warning(request, "Un trajet est déjà en cours.")
        return redirect("tracker:index")
    try:
        trip = start_trip(request.user, idempotency_key)
    except IntegrityError:
        messages.warning(request, "Un trajet est déjà en cours; reprenez-le avant d'en démarrer un autre.")
        return redirect("tracker:index")
    return redirect("tracker:detail", trip_id=trip.pk)


@login_required
@require_POST
def record_point(request, trip_id):
    trip = get_object_or_404(
        Trip, pk=trip_id, user=request.user, status=Trip.Status.RECORDING
    )
    if len(request.body) > 4096:
        return JsonResponse({"error": "Données GPS trop volumineuses."}, status=413)
    try:
        payload = json.loads(request.body)
        point, created = add_point(trip, payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Corps JSON invalide."}, status=400)
    except GPSDataError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except GPSKeyUnavailable as exc:
        logger.error("GPS recording unavailable: encryption key is not configured.")
        return JsonResponse({"error": str(exc)}, status=503)
    return JsonResponse(
        {"accepted": True, "sequence": point.sequence, "duplicate": not created},
        status=201 if created else 200,
    )


@login_required
@require_POST
def complete(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    try:
        trip = finish_trip(trip)
    except GPSKeyUnavailable as exc:
        logger.error("Trip completion unavailable: encryption key is not configured.")
        messages.error(request, str(exc))
        return redirect("tracker:detail", trip_id=trip.pk)
    except GPSDataError as exc:
        messages.error(request, str(exc))
        return redirect("tracker:detail", trip_id=trip.pk)
    if trip.prediction_status == "unavailable":
        messages.info(
            request,
            "Trajet enregistré. Le modèle LightGBM n'est pas configuré ; "
            "aucune prédiction automatique n'a été affichée.",
        )
    elif trip.prediction_status == "low_confidence":
        messages.warning(
            request,
            "Le modèle n'a pas reconnu le mode avec une confiance suffisante.",
        )
    elif trip.prediction_status == "failed":
        messages.error(request, "L'analyse IA a échoué. Consultez le détail et réessayez.")
    else:
        messages.success(request, "Trajet terminé et analysé.")
    return redirect("tracker:detail", trip_id=trip.pk)


@login_required
def detail(request, trip_id):
    trip = _owned_trip(request, trip_id)
    map_points = _map_points(trip)
    last_sequence = trip.gps_points.order_by("-sequence").values_list(
        "sequence", flat=True
    ).first()
    return render(
        request,
        "tracker/detail.html",
        {
            "trip": trip,
            "map_points": map_points,
            "has_gps_points": trip.gps_points.exists(),
            "next_sequence": (last_sequence + 1) if last_sequence is not None else 0,
            "prediction_confidence_pct": (
                round(trip.prediction_confidence * 100)
                if trip.prediction_confidence is not None else None
            ),
            "model_artifact_configured": model_artifact_configured(),
        },
    )


@login_required
def heatmap(request):
    points = GPSPoint.objects.filter(trip__user=request.user).order_by("-recorded_at")[:2000]
    heat_points = []
    error = ""
    try:
        for point in points:
            latitude, longitude = decrypt_coordinates(
                point.latitude_ciphertext, point.longitude_ciphertext
            )
            heat_points.append([latitude, longitude])
    except GPSKeyUnavailable:
        logger.error("Personal heatmap unavailable: GPS encryption key is not configured.")
        error = "La clé GPS n'est pas configurée; la heatmap ne peut pas être déchiffrée."
    except GPSDataError:
        logger.error("Personal heatmap unavailable: stored GPS ciphertext is invalid.")
        error = "Certains points GPS sont illisibles."
    return render(
        request,
        "tracker/heatmap.html",
        {"heat_points": heat_points, "heatmap_error": error},
    )


@login_required
@require_POST
def retry_analysis(request, trip_id):
    trip = get_object_or_404(
        Trip, pk=trip_id, user=request.user, status=Trip.Status.COMPLETED
    )
    try:
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
        result = predict_transport(samples)
    except GPSKeyUnavailable as exc:
        messages.error(request, str(exc))
        return redirect("tracker:detail", trip_id=trip.pk)
    except GPSDataError:
        logger.error("Trip analysis unavailable: stored GPS ciphertext is invalid.")
        messages.error(request, "Les points GPS ne peuvent pas être déchiffrés.")
        return redirect("tracker:detail", trip_id=trip.pk)
    trip.prediction_status = result["status"]
    mode = result.get("mode")
    supported = {value for value, _ in Trip.TransportMode.choices}
    if mode not in supported and result["status"] == "complete":
        result = {**result, "status": "low_confidence", "mode": None}
    trip.prediction_status = result["status"]
    trip.detected_transport_mode = mode if mode in supported else ""
    trip.prediction_confidence = result.get("confidence")
    selected_mode = trip.confirmed_transport_mode or (
        trip.detected_transport_mode
        if trip.prediction_status == "complete" else ""
    )
    if (
        trip.prediction_status == "complete"
        and not trip.confirmed_transport_mode
        and selected_mode
    ):
        _replace_segments(
            trip,
            segment_points(samples),
            selected_mode,
            trip.prediction_confidence,
        )
        trip.save(update_fields=("prediction_status", "detected_transport_mode",
                                 "prediction_confidence", "co2_kg", "updated_at"))
    elif selected_mode:
        refresh_confirmed_carbon(trip)
    else:
        refresh_confirmed_carbon(trip)
        trip.save()
    if trip.prediction_status == "complete":
        messages.success(request, "Analyse du trajet terminée.")
    elif trip.prediction_status == "unavailable":
        messages.warning(request, "Le modèle LightGBM n'est pas configuré.")
    elif trip.prediction_status == "low_confidence":
        messages.warning(request, "La confiance du modèle est insuffisante pour attribuer un mode.")
    else:
        messages.error(request, "L'analyse a échoué; aucune nouvelle prédiction n'a été enregistrée.")
    return redirect("tracker:detail", trip_id=trip.pk)


@login_required
@require_http_methods(["GET", "POST"])
def update(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    form = TripUpdateForm(request.POST or None, instance=trip)
    if request.method == "POST" and form.is_valid():
        trip = form.save()
        refresh_confirmed_carbon(trip)
        messages.success(request, "Le trajet a été mis à jour.")
        return redirect("tracker:detail", trip_id=trip.pk)
    return render(request, "tracker/trip_form.html", {"form": form, "trip": trip})


@login_required
@require_http_methods(["GET", "POST"])
def delete(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    if request.method == "POST":
        trip.delete()
        messages.success(request, "Le trajet et ses points GPS chiffrés ont été supprimés.")
        return redirect("tracker:index")
    return render(request, "tracker/confirm_delete.html", {"trip": trip})


@login_required
def compare(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    real_mode = trip.confirmed_transport_mode or (
        trip.detected_transport_mode
        if trip.prediction_status == "complete" else ""
    )
    alternatives = []
    actual = None
    if real_mode and trip.distance_km > 0:
        from carbon_service.services import calculate_trip_emissions

        actual = calculate_trip_emissions(trip.distance_km, real_mode)
        for mode, label in Trip.TransportMode.choices:
            if mode == real_mode:
                continue
            emissions = calculate_alternative_emissions(trip.distance_km, mode)
            savings = calculate_carbon_savings(actual, emissions)
            reduction = (
                (savings / actual * Decimal("100")).quantize(Decimal("0.1"))
                if actual > 0 else None
            )
            alternatives.append(
                {
                    "mode": mode,
                    "label": label,
                    "co2": emissions,
                    "savings": savings,
                    "reduction": reduction,
                    "estimated": True,
                }
            )
        maximum_emissions = max(
            [actual, *(alternative["co2"] for alternative in alternatives)]
        )
        for alternative in alternatives:
            alternative["bar_percentage"] = round(
                alternative["co2"] * 100 / maximum_emissions
            ) if maximum_emissions else 0
        real_bar_percentage = round(actual * 100 / maximum_emissions) if maximum_emissions else 0
    else:
        real_bar_percentage = 0
    return render(
        request,
        "tracker/compare.html",
        {
            "trip": trip,
            "real_mode": real_mode,
            "real_emissions": actual,
            "real_bar_percentage": real_bar_percentage,
            "alternatives": alternatives,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def import_gpx(request):
    form = GPXUploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            samples = parse_gpx(form.cleaned_data["file"])
            trip = create_imported_trip(
                request.user, form.cleaned_data["file"].name, samples
            )
        except (GPSDataError, GPSKeyUnavailable) as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "Le trajet GPX a été importé.")
            return redirect("tracker:detail", trip_id=trip.pk)
    return render(request, "tracker/import_gpx.html", {"form": form})


@login_required
def export_gpx(request, trip_id):
    trip = get_object_or_404(Trip, pk=trip_id, user=request.user)
    try:
        points = [
            {
                "latitude": latitude,
                "longitude": longitude,
                "timestamp": point.recorded_at,
            }
            for point in trip.gps_points.order_by("sequence")
            for latitude, longitude in [
                decrypt_coordinates(point.latitude_ciphertext, point.longitude_ciphertext)
            ]
        ]
        if not points:
            return HttpResponse(
                "Aucun point GPS valide n'est disponible pour l'export.",
                status=400,
                content_type="text/plain; charset=utf-8",
            )
        contents = build_gpx(points)
    except GPSKeyUnavailable as exc:
        return HttpResponse(str(exc), status=503, content_type="text/plain; charset=utf-8")
    except GPSDataError:
        logger.error("GPX export failed: stored GPS ciphertext is invalid.")
        return HttpResponse(
            "Les points GPS de ce trajet sont illisibles.",
            status=409,
            content_type="text/plain; charset=utf-8",
        )
    response = HttpResponse(contents, content_type="application/gpx+xml")
    response["Content-Disposition"] = f'attachment; filename="greenmove-{trip.pk}.gpx"'
    return response


def manifest(_request):
    _ = _request
    return JsonResponse(
        {
            "name": "GreenMove Mobility Tracker",
            "short_name": "GreenMove",
            "start_url": "/tracker/",
            "display": "standalone",
            "background_color": "#f8faf7",
            "theme_color": "#335c45",
            "description": "Suivi privé des déplacements GreenMove.",
            "icons": [
                {
                    "src": "/static/tracker/greenmove.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "any maskable",
                }
            ],
        },
        content_type="application/manifest+json",
    )


def service_worker(request):
    response = render(request, "tracker/service-worker.js", content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/tracker/"
    response["Cache-Control"] = "no-cache"
    return response


def offline(request):
    return render(request, "tracker/offline.html")
