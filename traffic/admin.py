from django.contrib import admin
from .forms import MonitoringPointForm, TrafficSnapshotForm
from .models import MonitoringPoint, TrafficSnapshot


@admin.register(MonitoringPoint)
class MonitoringPointAdmin(admin.ModelAdmin):
    form = MonitoringPointForm
    list_display = ('name', 'latitude', 'longitude', 'profile', 'is_active')
    list_filter = ('profile', 'is_active')
    search_fields = ('name',)


@admin.register(TrafficSnapshot)
class TrafficSnapshotAdmin(admin.ModelAdmin):
    form = TrafficSnapshotForm
    list_display = ('point', 'timestamp', 'congestion', 'current_speed', 'free_flow_speed', 'precipitation_mm', 'source')
    list_filter = ('point', 'source', 'is_holiday')
    date_hierarchy = 'timestamp'
    raw_id_fields = ('point',)