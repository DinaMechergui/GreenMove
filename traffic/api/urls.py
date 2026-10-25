from django.urls import path

from . import views

app_name = 'traffic_api'

urlpatterns = [
    path('points/', views.points, name='points'),
    path('forecast/', views.forecast, name='forecast'),
    path('heatmap/', views.heatmap, name='heatmap'),
    path('best-time/', views.best_time, name='best_time'),
    path('history/', views.history, name='history'),
]
