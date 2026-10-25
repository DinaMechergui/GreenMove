from django.contrib import admin

from .models import CarbonBudget, RecurringTrip, TripRecord


@admin.register(TripRecord)
class TripRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'mode', 'distance_km', 'co2_kg')
    list_filter = ('mode',)
    search_fields = ('user__username',)
    date_hierarchy = 'date'


@admin.register(RecurringTrip)
class RecurringTripAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'weekday', 'arrival_time', 'distance_km')
    list_filter = ('weekday',)


@admin.register(CarbonBudget)
class CarbonBudgetAdmin(admin.ModelAdmin):
    list_display = ('user', 'month', 'budget_kg', 'alert_level')
