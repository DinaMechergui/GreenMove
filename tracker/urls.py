from django.urls import path
from . import views, gps_views

app_name = 'tracker'

urlpatterns = [
    path('', views.coming_soon, name='index'),
    path('trips/<int:pk>/gps/', gps_views.trip_gps, name='trip_gps'),
]
