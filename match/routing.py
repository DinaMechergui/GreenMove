"""
Routage WebSocket pour l'application Match (MobilityMatch AI).
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/match/live/(?P<user_id>\w+)/$', consumers.MatchNotificationConsumer.as_asgi()),
    re_path(r'ws/match/rides/$', consumers.RideUpdatesConsumer.as_asgi()),
    re_path(r'ws/match/chat/(?P<room_id>\d+)/$', consumers.ChatConsumer.as_asgi()),
    re_path(r'ws/match/track/(?P<token>[-\w]+)/$', consumers.TrackingConsumer.as_asgi()),
    re_path(r'ws/match/sos/(?P<ride_id>\d+)/$', consumers.SOSConsumer.as_asgi()),
]
