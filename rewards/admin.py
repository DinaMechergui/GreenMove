"""
Administration Django pour l'application EcoRewards & Gamification.
Architecture simplifiée, ergonomique et épurée pour la soutenance.
"""
from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
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


# ==============================================================================
# INLINES ÉLÉGANTS (Centralisation des sous-tables dans les fiches principales)
# ==============================================================================

class RewardItemInline(admin.TabularInline):
    """Permet de gérer les articles/récompenses directement dans la fiche du Partenaire."""
    model = RewardItem
    extra = 1
    fields = ('title', 'points_cost', 'discount_label', 'stock', 'is_active')
    show_change_link = True


class UserBadgeInline(admin.TabularInline):
    """Affiche les utilisateurs ayant débloqué ce badge directement sous le Badge."""
    model = UserBadge
    extra = 0
    fields = ('user', 'earned_at', 'is_viewed')
    readonly_fields = ('earned_at',)
    autocomplete_fields = ('user',)
    show_change_link = True


# ==============================================================================
# MODÈLES PRINCIPAUX VISIBLES DANS LA BARRE LATÉRALE (5 Entrées Clés)
# ==============================================================================

@admin.register(UserGamificationProfile)
class UserGamificationProfileAdmin(admin.ModelAdmin):
    """Fiche centrale de gamification utilisateur avec synthèse complète."""
    list_display = (
        'user',
        'level_badge_display',
        'points_display',
        'total_co2_saved_kg',
        'trees_display',
        'streak_days',
        'district',
        'organization',
        'kmeans_cluster_label',
    )
    list_filter = ('district', 'organization', 'kmeans_cluster')
    search_fields = ('user__username', 'user__email', 'district', 'organization')
    ordering = ('-total_co2_saved_kg',)
    readonly_fields = (
        'level_badge_display',
        'points_display',
        'trees_display',
        'recent_transactions_summary',
        'active_challenges_summary',
        'earned_badges_summary',
        'created_at',
        'updated_at',
    )
    fieldsets = (
        (_('Utilisateur & Localisation'), {
            'fields': ('user', 'district', 'organization')
        }),
        (_('Progression & Niveaux'), {
            'fields': ('level_badge_display', 'points_display', 'streak_days', 'last_activity_date')
        }),
        (_('Impact Écologique'), {
            'fields': ('total_co2_saved_kg', 'monthly_co2_saved_kg', 'trees_display')
        }),
        (_('Segmentation & IA (KMeans)'), {
            'fields': ('kmeans_cluster', 'kmeans_cluster_label', 'last_profiled_at')
        }),
        (_('Synthèse Activités & Récompenses'), {
            'fields': ('earned_badges_summary', 'active_challenges_summary', 'recent_transactions_summary')
        }),
    )

    def level_badge_display(self, obj):
        info = obj.current_level_info
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 4px 12px; border-radius: 999px; font-weight: 600; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; line-height: 1.2; box-shadow: 0 1px 2px rgba(0,0,0,0.08);">'
            '<i class="bi {}" style="font-size: 0.85rem;"></i> {}'
            '</span>',
            info['color'], info['icon'], info['title']
        )
    level_badge_display.short_description = "Niveau actuel"

    def points_display(self, obj):
        return format_html('<b>{}</b> pts', obj.current_points)
    points_display.short_description = "Éco-Points"

    def trees_display(self, obj):
        return format_html('🌳 <b>{}</b> arbres', obj.trees_equivalent)
    trees_display.short_description = "Équiv. Arbres"

    def recent_transactions_summary(self, obj):
        txs = obj.user.eco_transactions.all()[:6]
        if not txs:
            return "Aucune transaction enregistrée."
        lines = []
        for t in txs:
            color = "#2e7d32" if t.points >= 0 else "#c62828"
            sign = "+" if t.points >= 0 else ""
            lines.append(
                f"• <b>{t.created_at.strftime('%d/%m/%Y %H:%M')}</b> : "
                f"<span style='color:{color}; font-weight:bold;'>{sign}{t.points} pts</span> "
                f"({t.co2_saved_kg} kg CO₂) — {t.description}"
            )
        return format_html("<br>".join(lines))
    recent_transactions_summary.short_description = "Dernières transactions éco-points"

    def active_challenges_summary(self, obj):
        challenges = obj.user.personalized_challenges.all()[:5]
        if not challenges:
            return "Aucun défi personnalisé pour le moment."
        lines = []
        for c in challenges:
            lines.append(f"• <b>[{c.get_difficulty_display()}]</b> {c.title} — Statut : {c.get_status_display()} ({c.progress_percentage}%)")
        return format_html("<br>".join(lines))
    active_challenges_summary.short_description = "Défis IA personnalisés"

    def earned_badges_summary(self, obj):
        badges = obj.user.earned_badges.select_related('badge')[:8]
        if not badges:
            return "Aucun badge débloqué pour l'instant."
        pills = []
        for ub in badges:
            b = ub.badge
            pills.append(
                f"<span style='background-color:{b.badge_color}; color:#fff; padding:3px 10px; border-radius:999px; font-size:12px; margin-right:6px; display:inline-flex; align-items:center; gap:4px; white-space:nowrap; margin-bottom:4px;'>"
                f"<i class='bi {b.icon}'></i> {b.name}</span>"
            )
        return format_html("".join(pills))
    earned_badges_summary.short_description = "Badges débloqués"


@admin.register(RewardPartner)
class RewardPartnerAdmin(admin.ModelAdmin):
    """Partenaires commerciaux avec gestion directe de leurs offres en ligne."""
    list_display = ('name', 'category', 'location_name', 'active_rewards_count', 'is_verified')
    list_filter = ('category', 'is_verified')
    search_fields = ('name', 'location_name')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [RewardItemInline]

    def active_rewards_count(self, obj):
        count = obj.rewards.filter(is_active=True).count()
        return format_html('<b>{}</b> offre(s)', count)
    active_rewards_count.short_description = "Offres actives"


@admin.register(UserCoupon)
class UserCouponAdmin(admin.ModelAdmin):
    """Recherche rapide de coupons, validation et consultation des QR Codes."""
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


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    """Catalogue général des badges avec liste des détenteurs en ligne."""
    list_display = ('name', 'category', 'threshold_type', 'threshold_value', 'points_reward', 'holders_count', 'badge_icon_preview')
    list_filter = ('category', 'threshold_type')
    search_fields = ('name', 'description')
    prepopulated_fields = {'slug': ('name',)}
    inlines = [UserBadgeInline]

    def holders_count(self, obj):
        return obj.holders.count()
    holders_count.short_description = "Détenteurs"

    def badge_icon_preview(self, obj):
        return format_html('<i class="bi {}" style="font-size: 1.2rem; color: {};"></i> {}', obj.icon, obj.badge_color, obj.icon)
    badge_icon_preview.short_description = "Icône"


@admin.register(CollectiveChallenge)
class CollectiveChallengeAdmin(admin.ModelAdmin):
    """Défis communautaires avec jauge visuelle de CO2."""
    list_display = ('title', 'scope', 'target_entity_name', 'current_co2_kg', 'target_co2_kg', 'progress_bar', 'is_active', 'end_date')
    list_filter = ('scope', 'is_active')
    search_fields = ('title', 'target_entity_name')

    def progress_bar(self, obj):
        pct = obj.progress_percentage
        color = "#2e7d32" if pct >= 100 else "#0284c7"
        return format_html(
            '<div style="width:120px; background:#e0e0e0; border-radius:4px; overflow:hidden;">'
            '<div style="width:{}%; background:{}; height:14px; font-size:10px; color:#fff; text-align:center; line-height:14px;">{}%</div>'
            '</div>',
            pct, color, pct
        )
    progress_bar.short_description = "Progression"


# ==============================================================================
# SOUS-MODÈLES MASQUÉS DU MENU LATÉRAL (Accessibles via Inlines ou Relations)
# ==============================================================================

@admin.register(RewardItem)
class RewardItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'partner', 'points_cost', 'discount_label', 'stock', 'is_active')
    list_filter = ('partner__category', 'is_active')
    search_fields = ('title', 'partner__name')

    def has_module_permission(self, request):
        return False  # Masqué du menu latéral car géré dans Partenaire


@admin.register(UserBadge)
class UserBadgeAdmin(admin.ModelAdmin):
    list_display = ('user', 'badge', 'earned_at', 'is_viewed')
    list_filter = ('badge__category', 'earned_at')
    search_fields = ('user__username', 'badge__name')

    def has_module_permission(self, request):
        return False  # Masqué du menu latéral car géré sous chaque Badge


@admin.register(EcoTransaction)
class EcoTransactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'points', 'co2_saved_kg', 'transaction_type', 'description', 'created_at')
    list_filter = ('transaction_type', 'created_at')
    search_fields = ('user__username', 'description')
    readonly_fields = ('created_at',)

    def has_module_permission(self, request):
        return False  # Masqué du menu latéral car visualisé dans Profil Gamification


@admin.register(PersonalizedChallenge)
class PersonalizedChallengeAdmin(admin.ModelAdmin):
    list_display = ('user', 'title', 'difficulty', 'category', 'current_value', 'target_value', 'unit', 'status', 'end_date')
    list_filter = ('difficulty', 'category', 'status')
    search_fields = ('user__username', 'title')

    def has_module_permission(self, request):
        return False  # Masqué du menu latéral car visualisé dans Profil Gamification
