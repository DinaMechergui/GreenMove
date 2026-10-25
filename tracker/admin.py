from django.contrib import admin

from .models import GPSPoint, Trip, TripSegment


class GPSPointInline(admin.TabularInline):
    model = GPSPoint
    extra = 0
    fields = ("sequence", "recorded_at", "accuracy_m", "speed_mps")
    readonly_fields = fields
    can_delete = False


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "id", "user", "start_time", "status", "distance_km",
        "confirmed_transport_mode", "validation_status",
    )
    list_filter = ("status", "validation_status", "confirmed_transport_mode")
    search_fields = ("user__username", "title")
    readonly_fields = ("points_digest", "created_at", "updated_at")
    inlines = (GPSPointInline,)


@admin.register(TripSegment)
class TripSegmentAdmin(admin.ModelAdmin):
    list_display = ("trip", "order", "transport_mode", "distance_km", "co2_kg")
