"""
Configuration de production pour GreenMove.
"""
from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

if (
    SECRET_KEY.startswith('django-insecure-')
    or len(SECRET_KEY) < 50
    or len(set(SECRET_KEY)) < 5
):
    raise ImproperlyConfigured(
        'Production requires a strong SECRET_KEY from the environment.'
    )

render_hostname = config('RENDER_EXTERNAL_HOSTNAME', default='').strip()
ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default=render_hostname,
    cast=Csv(),
)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        'Set ALLOWED_HOSTS or RENDER_EXTERNAL_HOSTNAME in production.'
    )

if not DATABASE_URL:
    raise ImproperlyConfigured(
        'Set DATABASE_URL to the production PostgreSQL connection URL.'
    )

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default=f'https://{render_hostname}' if render_hostname else '',
    cast=Csv(),
)
if not CSRF_TRUSTED_ORIGINS:
    raise ImproperlyConfigured(
        'Set CSRF_TRUSTED_ORIGINS or RENDER_EXTERNAL_HOSTNAME in production.'
    )

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Sécurité HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
