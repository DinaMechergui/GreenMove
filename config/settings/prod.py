"""
Configuration de production pour GreenMove.
"""
from .base import *

DEBUG = False

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
