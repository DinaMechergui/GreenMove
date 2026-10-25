"""
URLs pour l'application Accounts.
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views, prefs_views

app_name = 'accounts'

urlpatterns = [
    # Authentification Web
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/edit-htmx/', views.profile_edit_htmx, name='profile_edit_htmx'),
    path('preferences/', prefs_views.preferences_view, name='preferences'),
    path('api/preferences/', prefs_views.APIPreferencesView.as_view(), name='api_preferences'),

    # API REST
    path('api/register/', views.APIRegisterView.as_view(), name='api_register'),
    path('api/profile/', views.APIProfileView.as_view(), name='api_profile'),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # RGPD
    path('data/export/', views.export_data_view, name='export_data'),
    path('data/delete/', views.delete_account_view, name='delete_account'),
    path('api/gdpr/export/', views.APIExportDataView.as_view(), name='api_export_data'),
    path('api/gdpr/delete/', views.APIDeleteAccountView.as_view(), name='api_delete_account'),
    path('api/audit/', views.APIAuditLogView.as_view(), name='api_audit'),
]
