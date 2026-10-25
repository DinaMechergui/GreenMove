"""
Sérialiseurs REST Framework pour MobilityMatch.
"""
from rest_framework import serializers
from .models import Ride, RideBooking, Review, RideGroup, ChatMessage
from accounts.serializers import UserSerializer


class RideSerializer(serializers.ModelSerializer):
    """Sérialiseur de trajet de covoiturage vert."""
    user = UserSerializer(read_only=True)
    distance_km = serializers.FloatField(read_only=True)
    estimated_co2_saved = serializers.FloatField(read_only=True)
    road_distance_km = serializers.SerializerMethodField()

    def get_road_distance_km(self, obj) -> float:
        from .services.costs import ride_effective_distance_km
        return ride_effective_distance_km(obj)

    class Meta:
        model = Ride
        fields = (
            'id',
            'user',
            'ride_type',
            'status',
            'origin_address',
            'origin_lat',
            'origin_lon',
            'destination_address',
            'destination_lat',
            'destination_lon',
            'departure_datetime',
            'seats_available',
            'price_tnd',
            'is_recurring',
            'recurring_days',
            'description',
            'distance_km',
            'road_distance_km',
            'estimated_co2_saved',
            'created_at',
        )
        read_only_fields = ('id', 'user', 'distance_km', 'road_distance_km', 'estimated_co2_saved', 'created_at')


class RideBookingSerializer(serializers.ModelSerializer):
    """Sérialiseur de demande de réservation."""
    passenger = UserSerializer(read_only=True)
    ride = RideSerializer(read_only=True)

    class Meta:
        model = RideBooking
        fields = (
            'id',
            'ride',
            'passenger',
            'status',
            'seats_requested',
            'message',
            'created_at',
        )
        read_only_fields = ('id', 'passenger', 'created_at')


class ReviewSerializer(serializers.ModelSerializer):
    """Sérialiseur d'avis post-trajet (score de fiabilité)."""
    reviewer = UserSerializer(read_only=True)
    rating = serializers.IntegerField(min_value=1, max_value=5)

    class Meta:
        model = Review
        fields = ('id', 'ride', 'reviewer', 'reviewed_user', 'rating', 'comment', 'created_at')
        read_only_fields = ('id', 'reviewer', 'reviewed_user', 'created_at')


class RideGroupSerializer(serializers.ModelSerializer):
    """Sérialiseur de groupe DBSCAN persisté."""
    mode_display = serializers.CharField(source='get_mode_display', read_only=True)
    ride_ids = serializers.PrimaryKeyRelatedField(
        source='rides', many=True, read_only=True
    )

    class Meta:
        model = RideGroup
        fields = (
            'id', 'cluster_id', 'mode', 'mode_display', 'label',
            'origin_lat', 'origin_lon', 'destination_lat', 'destination_lon',
            'ride_ids', 'created_at',
        )


class ChatMessageSerializer(serializers.ModelSerializer):
    """Sérialiseur de message de chat (sender null = suggestion système)."""
    sender_name = serializers.SerializerMethodField()

    class Meta:
        model = ChatMessage
        fields = ('id', 'room', 'sender', 'sender_name', 'content', 'is_suggestion', 'created_at')
        read_only_fields = fields

    def get_sender_name(self, obj):
        if obj.sender is None:
            return 'GreenMove'
        return obj.sender.get_full_name() or obj.sender.username
