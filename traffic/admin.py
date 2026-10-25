from django.contrib import admin
from .models import MonitoringPoint, TrafficSnapshot


@admin.register(MonitoringPoint)
class MonitoringPointAdmin(admin.ModelAdmin):
    list_display = ('name', 'profile', 'is_active')


@admin.register(TrafficSnapshot)
class TrafficSnapshotAdmin(admin.ModelAdmin):
    list_display = ('point', 'timestamp', 'congestion', 'precipitation_mm', 'source')
    list_filter = ('point', 'source')