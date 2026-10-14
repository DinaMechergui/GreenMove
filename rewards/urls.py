from django.urls import path
from . import views

app_name = 'rewards'

urlpatterns = [
    path('', views.coming_soon, name='index'),
]
