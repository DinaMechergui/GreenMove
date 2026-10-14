from django.urls import path
from . import views

app_name = 'traffic'

urlpatterns = [
    path('', views.coming_soon, name='index'),
]
