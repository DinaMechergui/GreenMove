"""Authenticated REST endpoints using the project's DRF/JWT configuration."""

from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Trip
from .permissions import IsTripOwner
from .serializers import (
    GPSPointInputSerializer,
    GPSPointAcceptedSerializer,
    TripSerializer,
    TripStartSerializer,
)
from .services.gps_service import GPSDataError, GPSKeyUnavailable
from .services.trip_service import (
    add_point,
    finish_trip,
    refresh_confirmed_carbon,
    start_trip,
)


class TripListCreateAPI(generics.ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = TripSerializer

    def get_queryset(self):
        return Trip.objects.filter(user=self.request.user).prefetch_related("segments")

    @extend_schema(request=TripStartSerializer, responses={201: TripSerializer})
    def create(self, request, *args, **kwargs):
        input_serializer = TripStartSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        try:
            trip = start_trip(
                request.user, input_serializer.validated_data["idempotency_key"]
            )
        except IntegrityError:
            return Response(
                {"detail": "Un trajet est déjà en cours."},
                status=status.HTTP_409_CONFLICT,
            )
        title = input_serializer.validated_data.get("title", "")
        if title and trip.title != title:
            trip.title = title
            trip.save(update_fields=("title", "updated_at"))
        return Response(
            TripSerializer(trip, context=self.get_serializer_context()).data,
            status=status.HTTP_201_CREATED,
        )


class TripDetailAPI(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (IsAuthenticated, IsTripOwner)
    serializer_class = TripSerializer
    lookup_field = "id"
    lookup_url_kwarg = "trip_id"

    def get_queryset(self):
        return Trip.objects.filter(user=self.request.user).prefetch_related("segments")

    def perform_update(self, serializer):
        trip = serializer.save()
        refresh_confirmed_carbon(trip)


class TripPointAPI(APIView):
    permission_classes = (IsAuthenticated, IsTripOwner)

    @extend_schema(
        request=GPSPointInputSerializer,
        responses={201: GPSPointAcceptedSerializer, 200: GPSPointAcceptedSerializer},
    )
    def post(self, request, trip_id):
        trip = get_object_or_404(
            Trip,
            id=trip_id,
            user=request.user,
            status=Trip.Status.RECORDING,
        )
        self.check_object_permissions(request, trip)
        input_serializer = GPSPointInputSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        payload = dict(input_serializer.validated_data)
        try:
            point, created = add_point(trip, payload)
        except GPSKeyUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except GPSDataError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(
            {"accepted": True, "sequence": point.sequence, "duplicate": not created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class TripCompleteAPI(APIView):
    permission_classes = (IsAuthenticated, IsTripOwner)

    @extend_schema(request=None, responses=TripSerializer)
    def post(self, request, trip_id):
        trip = get_object_or_404(Trip, id=trip_id, user=request.user)
        self.check_object_permissions(request, trip)
        try:
            trip = finish_trip(trip)
        except GPSKeyUnavailable as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        except GPSDataError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        return Response(TripSerializer(trip).data)
