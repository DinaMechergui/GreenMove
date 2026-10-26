"""
Configuration spécifique pour le développement local.
"""
from .base import *

DEBUG = True

# Sécurité assouplie en développement local
ALLOWED_HOSTS = ['*']

# Affichage des emails dans la console au lieu d'envoyer réellement
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# En local, les tâches Celery s'exécutent de façon synchrone : aucun Redis/worker
# n'est nécessaire et la page /match/ai/metrics/ affiche ses résultats directement.
# En production (prod.py), le mode asynchrone réel est utilisé avec Redis.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES_EXCEPTIONS = True
