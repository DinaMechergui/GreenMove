"""
Paquet de configuration du projet GreenMove.
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
