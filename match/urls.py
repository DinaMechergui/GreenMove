"""
URLs pour l'application MobilityMatch.
"""
from django.urls import path
from . import views

app_name = 'match'

urlpatterns = [
    # Vues Web
    path('', views.search_rides, name='search'),
    path('create/', views.create_ride, name='create_ride'),
    path('<int:pk>/', views.ride_detail, name='ride_detail'),
    path('<int:pk>/book/', views.book_ride, name='book_ride'),
    path('bookings/<int:booking_id>/manage/', views.manage_booking, name='manage_booking'),
    path('<int:pk>/review/', views.create_review, name='create_review'),
    path('<int:pk>/tracking-link/', views.create_tracking_link, name='create_tracking_link'),
    path('<int:pk>/sos/', views.trigger_sos, name='trigger_sos'),
    path('<int:pk>/cancel/', views.cancel_ride, name='cancel_ride'),
    path('my-rides/', views.my_rides, name='my_rides'),

    # Temps réel
    path('chat/<int:pk>/', views.chat_room, name='chat_room'),
    path('chat/room/<int:room_id>/send/', views.chat_post_message, name='chat_post_message'),
    path('chat/room/<int:room_id>/messages/', views.chat_get_messages, name='chat_get_messages'),
    path('live/<uuid:token>/', views.live_tracking, name='live_tracking'),

    # Outils IA
    path('meeting-point/', views.meeting_point, name='meeting_point'),
    path('groups/', views.trip_groups, name='groups'),
    path('tools/split/', views.split_calculator, name='split_calculator'),
    path('ai/metrics/', views.ai_metrics, name='ai_metrics'),
    path('ai/metrics/status/', views.ai_metrics_status, name='ai_metrics_status'),

    # Endpoints API REST
    path('api/rides/', views.APIRideListCreateView.as_view(), name='api_ride_list'),
    path('api/rides/<int:pk>/', views.APIRideDetailView.as_view(), name='api_ride_detail'),
    path('api/find-matches/', views.APIFindMatchesView.as_view(), name='api_find_matches'),
    path('api/meeting-point/', views.APIMeetingPointView.as_view(), name='api_meeting_point'),
    path('api/groups/', views.APIRideGroupsView.as_view(), name='api_groups'),
]
