"""Accès aux données GPS d'un trajet (audité). Fichier séparé de views.py pour faciliter le merge."""
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from accounts.audit import log_event
from accounts.models import AuditLog
from accounts.permissions import has_role
from accounts.signals import ADMIN_GROUP

from .models import Trip
from .services.gps_service import GPSDataError, GPSKeyUnavailable, decrypt_coordinates

logger = logging.getLogger(__name__)


@login_required
def trip_gps(request, pk):
    """Retourne la trace GPS d'un trajet (propriétaire ou admin) et journalise l'accès."""
    trip = get_object_or_404(Trip, pk=pk)
    if trip.user_id != request.user.id and not (request.user.is_superuser or has_role(request.user, ADMIN_GROUP)):
        return JsonResponse({'detail': 'Accès refusé.'}, status=403)
    log_event(AuditLog.Action.GPS_ACCESS, request.user, detail=f'trip #{trip.pk} (owner={trip.user_id})',
              request=request)
    try:
        points = []
        for point in trip.gps_points.order_by("sequence"):
            latitude, longitude = decrypt_coordinates(
                point.latitude_ciphertext, point.longitude_ciphertext
            )
            points.append({
                "sequence": point.sequence,
                "latitude": latitude,
                "longitude": longitude,
                "recorded_at": point.recorded_at.isoformat(),
            })
    except GPSKeyUnavailable:
        logger.error("Audited GPS access unavailable: encryption key is not configured.")
        return JsonResponse({"detail": "Les coordonnées GPS ne sont pas disponibles."}, status=503)
    except GPSDataError:
        logger.error("Audited GPS access failed: stored GPS ciphertext is invalid.")
        return JsonResponse({"detail": "Les coordonnées GPS sont illisibles."}, status=409)
    return JsonResponse({'trip': str(trip.pk), 'points': points})
