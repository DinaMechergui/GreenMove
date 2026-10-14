"""
Administration Django pour l'application Match.
"""
from django.contrib import admin
from .models import (
    Ride, RideBooking, Review, ChatRoom, ChatMessage,
    TrackingLink, SOSAlert, RideGroup,
)


@admin.register(Ride)
class RideAdmin(admin.ModelAdmin):
    list_display = ('user', 'ride_type', 'origin_address', 'destination_address', 'departure_datetime', 'seats_available', 'status')
    list_filter = ('ride_type', 'status', 'is_recurring')
    search_fields = ('origin_address', 'destination_address', 'user__username', 'user__first_name', 'user__last_name')
    date_hierarchy = 'departure_datetime'


@admin.register(RideBooking)
class RideBookingAdmin(admin.ModelAdmin):
    list_display = ('ride', 'passenger', 'seats_requested', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('passenger__username', 'ride__origin_address', 'ride__destination_address')


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ('reviewed_user', 'reviewer', 'ride', 'rating', 'created_at')
    list_filter = ('rating', 'created_at')
    search_fields = ('reviewer__username', 'reviewed_user__username', 'comment')


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    readonly_fields = ('sender', 'content', 'is_suggestion', 'created_at')


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('ride', 'created_at')
    inlines = [ChatMessageInline]


@admin.register(TrackingLink)
class TrackingLinkAdmin(admin.ModelAdmin):
    list_display = ('ride', 'owner', 'token', 'is_active', 'expires_at', 'created_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('owner__username', 'token')


@admin.register(SOSAlert)
class SOSAlertAdmin(admin.ModelAdmin):
    list_display = ('user', 'ride', 'status', 'latitude', 'longitude', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'message')


@admin.register(RideGroup)
class RideGroupAdmin(admin.ModelAdmin):
    list_display = ('cluster_id', 'mode', 'label', 'created_at')
    list_filter = ('mode',)
    search_fields = ('label',)
    filter_horizontal = ('rides', 'members')
