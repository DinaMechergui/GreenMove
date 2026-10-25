"""Sérialiseurs DRF pour EcoPlanner."""
from rest_framework import serializers
from .models import TripRecord, RecurringTrip, CarbonBudget, Mode


class TripRecordSerializer(serializers.ModelSerializer):
    """CRUD complet sur les trajets effectués."""
    co2_kg = serializers.FloatField(read_only=True)
    mode_label = serializers.SerializerMethodField()

    class Meta:
        model = TripRecord
        fields = ('id', 'date', 'mode', 'mode_label', 'distance_km',
                  'duration_min', 'co2_kg', 'source_trip_id')
        read_only_fields = ('id', 'co2_kg', 'source_trip_id')

    def get_mode_label(self, obj):
        return obj.get_mode_display()

    def validate_distance_km(self, value):
        if value <= 0:
            raise serializers.ValidationError('La distance doit être positive.')
        return value

    def validate_duration_min(self, value):
        if value < 0:
            raise serializers.ValidationError('La durée ne peut pas être négative.')
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class RecurringTripSerializer(serializers.ModelSerializer):
    weekday_label = serializers.SerializerMethodField()

    class Meta:
        model = RecurringTrip
        fields = ('id', 'label', 'weekday', 'weekday_label', 'arrival_time',
                  'distance_km', 'origin', 'destination')
        read_only_fields = ('id',)

    def get_weekday_label(self, obj):
        return obj.get_weekday_display()

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class CarbonBudgetSerializer(serializers.ModelSerializer):
    class Meta:
        model = CarbonBudget
        fields = ('id', 'month', 'budget_kg', 'alert_level')
        read_only_fields = ('id', 'alert_level')

    def validate_budget_kg(self, value):
        if value <= 0:
            raise serializers.ValidationError("Le budget doit être positif.")
        return value

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)
