"""Sérialiseurs de sortie (format JSON + documentation OpenAPI)."""
from django.utils import timezone
from rest_framework import serializers

from traffic.models import MonitoringPoint, TrafficSnapshot


class MonitoringPointSerializer(serializers.ModelSerializer):
    lat = serializers.FloatField(source='latitude')
    lon = serializers.FloatField(source='longitude')

    class Meta:
        model = MonitoringPoint
        fields = ['id', 'name', 'lat', 'lon']


class ForecastSerializer(serializers.Serializer):
    point = MonitoringPointSerializer()
    datetime = serializers.DateTimeField()
    congestion = serializers.FloatField(help_text='0 = fluide, 1 = bloqué')
    level = serializers.CharField(help_text='fluide / modéré / dense / bloqué')
    level_code = serializers.CharField()
    data_source = serializers.CharField()


class HeatmapPointSerializer(serializers.Serializer):
    point = serializers.CharField()
    lat = serializers.FloatField()
    lon = serializers.FloatField()
    congestion = serializers.FloatField()
    level = serializers.CharField()
    level_code = serializers.CharField()


class HeatmapSerializer(serializers.Serializer):
    datetime = serializers.DateTimeField()
    precipitation_mm = serializers.FloatField()
    weather_available = serializers.BooleanField()
    data_source = serializers.CharField()
    points = HeatmapPointSerializer(many=True)


class BestTimeOptionSerializer(serializers.Serializer):
    departure = serializers.CharField()
    congestion = serializers.FloatField()
    duration_min = serializers.FloatField()
    precipitation_mm = serializers.FloatField()


class BestTimeSerializer(serializers.Serializer):
    origin = serializers.CharField()
    destination = serializers.CharField()
    base_duration_min = serializers.FloatField()
    duration_source = serializers.CharField()
    best = BestTimeOptionSerializer()
    worst = BestTimeOptionSerializer()
    time_saved_min = serializers.FloatField()
    message = serializers.CharField()
    options = BestTimeOptionSerializer(many=True)


class SnapshotSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    predicted = serializers.SerializerMethodField()

    class Meta:
        model = TrafficSnapshot
        fields = ['timestamp', 'label', 'congestion', 'current_speed', 'free_flow_speed',
                  'precipitation_mm', 'is_holiday', 'source', 'predicted']

    def get_label(self, obj):
        return timezone.localtime(obj.timestamp).strftime('%d/%m %H:%M')

    def get_predicted(self, obj):
        return self.context.get('predictions', {}).get(obj.pk)


class ErrorSerializer(serializers.Serializer):
    error = serializers.CharField()
