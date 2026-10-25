from django.urls import path

from . import crud_views, views

app_name = 'traffic'

urlpatterns = [
    # Pages de consultation & IA
    path('', views.traffic_map, name='index'),
    path('best-time/', views.best_time, name='best_time'),
    path('history/', views.history, name='history'),
    path('about-data/', views.about_data, name='about_data'),

    # CRUD MonitoringPoint
    path('points/', crud_views.PointListView.as_view(), name='point_list'),
    path('points/new/', crud_views.PointCreateView.as_view(), name='point_create'),
    path('points/<int:pk>/', crud_views.PointDetailView.as_view(), name='point_detail'),
    path('points/<int:pk>/edit/', crud_views.PointUpdateView.as_view(), name='point_update'),
    path('points/<int:pk>/delete/', crud_views.PointDeleteView.as_view(), name='point_delete'),

    # CRUD TrafficSnapshot
    path('snapshots/', crud_views.SnapshotListView.as_view(), name='snapshot_list'),
    path('snapshots/new/', crud_views.SnapshotCreateView.as_view(), name='snapshot_create'),
    path('snapshots/<int:pk>/', crud_views.SnapshotDetailView.as_view(), name='snapshot_detail'),
    path('snapshots/<int:pk>/edit/', crud_views.SnapshotUpdateView.as_view(), name='snapshot_update'),
    path('snapshots/<int:pk>/delete/', crud_views.SnapshotDeleteView.as_view(), name='snapshot_delete'),
]
