from django.urls import path
from . import views

app_name = 'tracker'

urlpatterns = [
    path('', views.coming_soon, name='index'),
]
