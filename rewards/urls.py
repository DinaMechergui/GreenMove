"""
URLs de l'application EcoRewards & Gamification.
"""
from django.urls import path
from . import views

app_name = 'rewards'

urlpatterns = [
    # Hub Principal de Gamification
    path('', views.index, name='index'),
    path('dashboard/', views.index, name='dashboard'),

    # Classements en temps réel
    path('leaderboard/', views.leaderboard_view, name='leaderboard'),

    # Défis personnalisés IA & Collectifs
    path('challenges/', views.challenges_view, name='challenges'),
    path('challenges/claim/<int:challenge_id>/', views.claim_challenge_reward, name='claim_challenge'),
    path('challenges/refresh/', views.refresh_personalized_challenges, name='refresh_challenges'),
    path('challenges/join/<int:challenge_id>/', views.join_collective_challenge, name='join_collective'),

    # Boutique Récompenses & Coupons
    path('catalog/', views.rewards_catalog, name='catalog'),
    path('catalog/redeem/<int:item_id>/', views.redeem_reward, name='redeem'),
    path('coupons/', views.my_coupons, name='my_coupons'),
    path('coupons/delete/<int:coupon_id>/', views.delete_user_coupon, name='delete_coupon'),
    path('coupons/verify/', views.verify_coupon_view, name='verify_coupon'),

    # Évaluation & Métriques Scientifiques IA KMeans (Grille 5TWIN)
    path('ai-evaluation/', views.ai_evaluation_view, name='ai_evaluation'),

    # Dashboard Administrateur d'Impact Global & Carte Leaflet
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),

    # Action Démo Interconnexion Modules (Trajet Roua -> Points Skander)
    path('demo/simulate-ride/', views.simulate_ride_completion_demo, name='simulate_ride_demo'),
]
