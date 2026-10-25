from rest_framework import serializers

from .models import Trip, TripSegment


class TripSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TripSegment
        fields = (
            "order",
            "transport_mode",
            "distance_km",
            "duration_seconds",
            "co2_kg",
            "confidence",
        )
        read_only_fields = fields


class TripSerializer(serializers.ModelSerializer):
    segments = TripSegmentSerializer(many=True, read_only=True)

    class Meta:
        model = Trip
        fields = (
            "id",
            "title",
            "start_time",
            "end_time",
            "status",
            "distance_km",
            "duration_seconds",
            "detected_transport_mode",
            "confirmed_transport_mode",
            "prediction_confidence",
            "prediction_status",
            "co2_kg",
            "validation_status",
            "validation_flags",
            "segments",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "start_time",
            "end_time",
            "status",
            "distance_km",
            "duration_seconds",
            "detected_transport_mode",
            "prediction_confidence",
            "prediction_status",
            "co2_kg",
            "validation_status",
            "validation_flags",
            "segments",
            "created_at",
            "updated_at",
        )


class TripStartSerializer(serializers.Serializer):
    idempotency_key = serializers.UUIDField()
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)


class GPSPointInputSerializer(serializers.Serializer):
    sequence = serializers.IntegerField(min_value=0)
    latitude = serializers.FloatField(min_value=-90, max_value=90)
    longitude = serializers.FloatField(min_value=-180, max_value=180)
    recorded_at = serializers.CharField()
    accuracy_m = serializers.FloatField(
        min_value=0, max_value=10000, required=False, allow_null=True
    )
    speed_mps = serializers.FloatField(
        min_value=0, max_value=150, required=False, allow_null=True
    )


class GPSPointAcceptedSerializer(serializers.Serializer):
    accepted = serializers.BooleanField()
    sequence = serializers.IntegerField()
    duplicate = serializers.BooleanField()
