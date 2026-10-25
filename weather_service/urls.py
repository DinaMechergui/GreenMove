from django.urls import path

from . import api

app_name = 'weather_api'

urlpatterns = [
    path('comfort/', api.comfort, name='comfort'),
    path('rain-alert/', api.rain_alert, name='rain_alert'),
    path('air-quality/', api.air_quality, name='air_quality'),
    path('best-hours/', api.best_hours, name='best_hours'),
]
