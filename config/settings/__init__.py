"""
Package de configuration Django pour GreenMove.
Charge la configuration selon la variable DJANGO_ENV ('dev' ou 'prod').
"""
import os
from decouple import config

env_mode = config('DJANGO_ENV', default='dev').lower()

if env_mode == 'prod':
    from .prod import *
else:
    from .dev import *
