"""
Configuration de production pour GreenMove.
"""
from .base import *
from django.core.exceptions import ImproperlyConfigured

DEBUG = False
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)

# Cache : Redis si configuré, sinon LocMemCache
redis_url = config('REDIS_URL', default=config('CACHE_URL', default='')).strip()
if redis_url:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.redis.RedisCache',
            'LOCATION': redis_url,
            'TIMEOUT': 3600,
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'greenmove-prod-cache',
            'TIMEOUT': 3600,
        }
    }

# Celery : mode eager synchrone si pas de Redis pour éviter tout blocage
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=not bool(redis_url), cast=bool)

# Clé secrète de production (avec repli robuste pour le premier déploiement Render)
if not SECRET_KEY or SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 50:
    SECRET_KEY = config(
        'SECRET_KEY',
        default='gm-prod-secure-key-esprit-5twin-2026-greenmove-platform-master-deployment-ready'
    )

render_hostname = config('RENDER_EXTERNAL_HOSTNAME', default='').strip()
allowed_hosts_default = f'{render_hostname},.onrender.com,localhost,127.0.0.1,*' if render_hostname else '.onrender.com,localhost,127.0.0.1,*'
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default=allowed_hosts_default, cast=Csv())

csrf_default = f'https://{render_hostname},https://*.onrender.com' if render_hostname else 'https://*.onrender.com'
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default=csrf_default, cast=Csv())

STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage',
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
SECURE_HSTS_PRELOAD = False
# La redirection SSL est assurée directement par le reverse proxy Render en amont.
# Laisser à False dans Django évite les boucles de redirection (301) lors des health checks internes de Render.
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True
