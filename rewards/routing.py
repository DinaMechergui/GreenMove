"""
Routage WebSocket pour l'application EcoRewards & Gamification.
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/rewards/leaderboard/$', consumers.LeaderboardConsumer.as_asgi()),
]
