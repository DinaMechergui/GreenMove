from django.urls import path
from . import api_views, views

app_name = 'tracker'

urlpatterns = [
    path("api/trips/", api_views.TripListCreateAPI.as_view(), name="api-list"),
    path("api/trips/<uuid:trip_id>/", api_views.TripDetailAPI.as_view(), name="api-detail"),
    path("api/trips/<uuid:trip_id>/points/", api_views.TripPointAPI.as_view(), name="api-point"),
    path("api/trips/<uuid:trip_id>/complete/", api_views.TripCompleteAPI.as_view(), name="api-complete"),
    path("", views.index, name="index"),
    path("heatmap/", views.heatmap, name="heatmap"),
    path("trips/start/", views.start, name="start"),
    path("trips/<uuid:trip_id>/", views.detail, name="detail"),
    path("trips/<uuid:trip_id>/points/", views.record_point, name="record-point"),
    path("trips/<uuid:trip_id>/complete/", views.complete, name="complete"),
    path("trips/<uuid:trip_id>/analysis/retry/", views.retry_analysis, name="retry-analysis"),
    path("trips/<uuid:trip_id>/edit/", views.update, name="update"),
    path("trips/<uuid:trip_id>/delete/", views.delete, name="delete"),
    path("trips/<uuid:trip_id>/compare/", views.compare, name="compare"),
    path("trips/<uuid:trip_id>/export.gpx", views.export_gpx, name="export-gpx"),
    path("import/gpx/", views.import_gpx, name="import-gpx"),
    path("manifest.webmanifest", views.manifest, name="manifest"),
    path("service-worker.js", views.service_worker, name="service-worker"),
    path("offline/", views.offline, name="offline"),
]
