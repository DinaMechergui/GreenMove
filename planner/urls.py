from django.urls import path
from . import views

app_name = 'planner'

urlpatterns = [
    path('', views.dashboard, name='index'),
    path('recurring/add/', views.add_recurring, name='add_recurring'),
    path('recurring/<int:pk>/delete/', views.delete_recurring, name='delete_recurring'),
    path('budget/set/', views.set_budget, name='set_budget'),
    path('calendar/export/', views.export_calendar, name='export_calendar'),
    path('calendar/import/', views.import_calendar, name='import_calendar'),
    path('report/download/', views.download_report, name='download_report'),
    path('report/email/', views.email_report, name='email_report'),
    path('api/explain/', views.api_explain, name='api_explain'),
    path('api/habits/', views.api_habits, name='api_habits'),
    path('api/plan/', views.api_plan, name='api_plan'),
    path('api/budget/', views.api_budget, name='api_budget'),
    path('api/simulate/', views.api_simulate, name='api_simulate'),
]
