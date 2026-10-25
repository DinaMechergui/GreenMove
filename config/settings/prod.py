"""
Configuration de production pour GreenMove.
"""
from .base import *

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

# En production, s'assurer que ALLOWED_HOSTS est strict
ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

# Sécurité HTTPS
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
