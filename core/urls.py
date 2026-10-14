"""
URLs pour l'application Core.
"""
from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('api/weather-snippet/', views.weather_snippet, name='weather_snippet'),
]
