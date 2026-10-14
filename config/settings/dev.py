"""
Configuration spécifique pour le développement local.
"""
from .base import *

DEBUG = True

# Sécurité assouplie en développement local
ALLOWED_HOSTS = ['*']

# Affichage des emails dans la console au lieu d'envoyer réellement
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
