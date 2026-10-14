"""
Administration Django pour le CustomUser de GreenMove.
"""
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'vehicle_type', 'eco_points', 'is_staff')
    list_filter = ('role', 'vehicle_type', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'first_name', 'last_name', 'home_address', 'work_address')
    ordering = ('-eco_points',)

    fieldsets = UserAdmin.fieldsets + (
        ('Profil Éco-Mobilité', {
            'fields': (
                'role',
                'vehicle_type',
                'vehicle_model',
                'available_seats',
                'eco_points',
                'avatar',
                'bio',
                'phone_number',
            )
        }),
        ('Trajet Domicile - Travail (Grand Tunis)', {
            'fields': (
                'home_address',
                'home_lat',
                'home_lon',
                'work_address',
                'work_lat',
                'work_lon',
                'departure_time_default',
            )
        }),
    )
