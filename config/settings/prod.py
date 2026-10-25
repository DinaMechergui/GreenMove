"""
Configuration de production pour GreenMove.
"""
from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)

# Le worker Celery et le serveur web partagent les statuts et artefacts du rapport.
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': config('CACHE_URL', default=config(
            'CELERY_BROKER_URL', default=config('REDIS_URL', default='redis://127.0.0.1:6379/0')
        )),
        'TIMEOUT': 3600,
    }
}

# Clé secrète de production (avec repli robuste pour le premier déploiement Render)
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 50:
    SECRET_KEY = config(
        'SECRET_KEY',
        default='gm-prod-secure-key-esprit-5twin-2026-greenmove-platform-master-deployment-ready'
    )

render_hostname = config('RENDER_EXTERNAL_HOSTNAME', default='').strip()
allowed_hosts_default = f'{render_hostname},.onrender.com,localhost,127.0.0.1' if render_hostname else '.onrender.com,localhost,127.0.0.1'
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=allowed_hosts_default, cast=Csv())

csrf_default = f'https://{render_hostname},https://*.onrender.com' if render_hostname else 'https://*.onrender.com'
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default=csrf_default, cast=Csv())

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
