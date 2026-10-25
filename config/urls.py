"""
Configuration des URLs principales pour GreenMove.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # Administration Django
    path('admin/', admin.site.urls),

    # Sélecteur de langue i18n
    path('i18n/', include('django.conf.urls.i18n')),

    # Applications Métier GreenMove
    path('', include('core.urls', namespace='core')),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    # Connexion Google (django-allauth) : callback /auth/google/login/callback/
    path('auth/', include('allauth.urls')),
    path('match/', include('match.urls', namespace='match')),
    path('tracker/', include('tracker.urls', namespace='tracker')),
    path('traffic/', include('traffic.urls', namespace='traffic')),
    path('planner/', include('planner.urls', namespace='planner')),
    path('rewards/', include('rewards.urls', namespace='rewards')),

    # API Documentation (Swagger / OpenAPI 3)
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/traffic/', include('traffic.api.urls', namespace='traffic_api')),
    path('api/weather/', include('weather_service.urls', namespace='weather_api')),
]

handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
