"""Accès aux données GPS d'un trajet (audité). Fichier séparé de views.py pour faciliter le merge."""
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from accounts.audit import log_event
from accounts.models import AuditLog
from accounts.permissions import has_role
from accounts.signals import ADMIN_GROUP

from .models import Trip


@login_required
def trip_gps(request, pk):
    """Retourne la trace GPS d'un trajet (propriétaire ou admin) et journalise l'accès."""
    trip = get_object_or_404(Trip, pk=pk)
    if trip.user_id != request.user.id and not (request.user.is_superuser or has_role(request.user, ADMIN_GROUP)):
        return JsonResponse({'detail': 'Accès refusé.'}, status=403)
    log_event(AuditLog.Action.GPS_ACCESS, request.user, detail=f'trip #{trip.pk} (owner={trip.user_id})',
              request=request)
    return JsonResponse({'trip': trip.pk, 'points': trip.gps_points})
