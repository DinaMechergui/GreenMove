from django.urls import path
from . import views

app_name = 'planner'

urlpatterns = [
    # Dashboard HTML
    path('', views.dashboard, name='index'),

    # Trajets habituels (CRUD)
    path('recurring/add/', views.add_recurring, name='add_recurring'),
    path('recurring/<int:pk>/delete/', views.delete_recurring, name='delete_recurring'),

    # Trajets effectués (CRUD HTML)
    path('trips/add/', views.add_trip_record, name='add_trip'),
    path('trips/<int:pk>/delete/', views.delete_trip_record, name='delete_trip'),

    # Budget carbone
    path('budget/set/', views.set_budget, name='set_budget'),

    # Calendrier
    path('calendar/export/', views.export_calendar, name='export_calendar'),
    path('calendar/import/', views.import_calendar, name='import_calendar'),

    # Rapport
    path('report/download/', views.download_report, name='download_report'),
    path('report/generate/', views.generate_report, name='generate_report'),
    path('report/status/', views.report_status, name='report_status'),
    path('report/email/', views.email_report, name='email_report'),

    # Export CSV
    path('export/csv/', views.export_csv, name='export_csv'),

    # API JSON (Chart.js / intégrations)
    path('api/explain/', views.api_explain, name='api_explain'),
    path('api/habits/', views.api_habits, name='api_habits'),
    path('api/plan/', views.api_plan, name='api_plan'),
    path('api/budget/', views.api_budget, name='api_budget'),
    path('api/simulate/', views.api_simulate, name='api_simulate'),
    path('api/metrics/', views.api_metrics, name='api_metrics'),
    path('api/leaderboard/', views.api_leaderboard, name='api_leaderboard'),

    # API REST DRF (documentée Swagger)
    path('api/trips/', views.TripRecordListCreateView.as_view(), name='api_trips'),
    path('api/trips/<int:pk>/', views.TripRecordDetailView.as_view(), name='api_trip_detail'),
    path('api/recurring/', views.RecurringTripListCreateView.as_view(), name='api_recurring'),
    path('api/recurring/<int:pk>/', views.RecurringTripDetailView.as_view(), name='api_recurring_detail'),
    path('api/carbon-budget/', views.CarbonBudgetView.as_view(), name='api_carbon_budget'),
    path('api/ai-metrics/', views.EcoMetricsAPIView.as_view(), name='api_ai_metrics'),
    path('api/eco-leaderboard/', views.EcoLeaderboardAPIView.as_view(), name='api_eco_leaderboard'),
]
