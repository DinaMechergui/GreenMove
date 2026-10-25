from django.urls import path

from . import views

app_name = 'traffic'

urlpatterns = [
    path('', views.traffic_map, name='index'),
    path('best-time/', views.best_time, name='best_time'),
    path('history/', views.history, name='history'),
    path('about-data/', views.about_data, name='about_data'),
]
