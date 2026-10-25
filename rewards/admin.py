"""
Administration Django pour l'application EcoRewards & Gamification.
"""
from django.contrib import admin
from django.utils.html import format_html
from .models import (
    UserGamificationProfile,
    Badge,
    UserBadge,
    EcoTransaction,
    PersonalizedChallenge,
    CollectiveChallenge,
    RewardPartner,
    RewardItem,
    UserCoupon,
)


@admin.register(UserGamificationProfile)
class UserGamificationProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'current_level_name', 'total_co2_saved_kg', 'streak_days', 'district', 'organization', 'kmeans_cluster_label')
    list_filter = ('district', 'organization', 'kmeans_cluster')
    search_fields = ('user__username', 'user__email', 'district', 'organization')
    ordering = ('-total_co2_saved_kg',)


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'threshold_type', 'threshold_value', 'points_reward', 'badge_icon_preview')
    list_filter = ('category', 'threshold_type')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}

    def badge_icon_preview(self, obj):
        return format_html('<i class="bi {}" style="font-size: 1.2rem; color: {};"></i> {}', obj.icon, obj.badge_color, obj.icon)
    badge_icon_preview.short_description = "Icône"


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'earned_at', 'is_viewed')
    list_filter = ('badge__category', 'earned_at')
    search_fields = ('user__username', 'badge__name')


@admin.register(EcoTransaction)
class EcoTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'co2_saved_kg', 'transaction_type', 'description', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)


@admin.register(PersonalizedChallenge)
class PersonalizedChallengeAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'difficulty', 'category', 'current_value', 'target_value', 'unit', 'status', 'end_date')
    list_filter = ('difficulty', 'category', 'status')
    search_fields = ('user__username', 'title')


@admin.register(CollectiveChallenge)
class CollectiveChallengeAdmin(admin.ModelAdmin):
    list_display = ('title', 'scope', 'target_entity_name', 'current_co2_kg', 'target_co2_kg', 'is_active', 'end_date')
    list_filter = ('scope', 'is_active')
    search_fields = ('title', 'target_entity_name')


@admin.register(RewardPartner)
class RewardPartnerAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'location_name', 'is_verified')
    list_filter = ('category', 'is_verified')
    search_fields = ('name', 'location_name')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(RewardItem)
class RewardItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'partner', 'points_cost', 'discount_label', 'stock', 'is_active')
    list_filter = ('partner__category', 'is_active')
    search_fields = ('title', 'partner__name')


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    list_display = ('coupon_code', 'user', 'reward', 'status', 'claimed_at', 'used_at')
    list_filter = ('status', 'claimed_at')
    search_fields = ('coupon_code', 'user__username', 'reward__title')
    readonly_fields = ('claimed_at', 'used_at', 'qr_code_preview')
    fields = ('user', 'reward', 'coupon_code', 'status', 'qr_code_preview', 'claimed_at', 'used_at')

    def qr_code_preview(self, obj):
        if obj and obj.qr_code_image:
            return format_html(
                '<div style="text-align:left;">'
                '<img src="{}" width="160" height="160" style="border-radius: 8px; border: 1px solid #ddd; background:#fff; padding:6px; box-shadow:0 2px 4px rgba(0,0,0,0.08);" /><br>'
                '<span style="color:#2e7d32; font-weight:600; font-size:12px;">✅ QR Code généré automatiquement</span>'
                '</div>',
                obj.qr_code_image
            )
        return "⚡ Le code unique et le QR Code seront automatiquement générés lors de l'enregistrement."
    qr_code_preview.short_description = "Aperçu QR Code"
