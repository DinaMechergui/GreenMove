"""
Configuration de base du projet GreenMove.
Contient les réglages communs à tous les environnements (développement et production).
"""

from pathlib import Path
from django.utils.translation import gettext_lazy as _
from decouple import config, Csv

# Répertoire racine du projet (dossier greenmove/)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Sécurité
SECRET_KEY = config('SECRET_KEY', default='django-insecure-greenmove-hackathon-2026-fallback-secret-key')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1,0.0.0.0', cast=Csv())

# Modèle Utilisateur personnalisé
AUTH_USER_MODEL = 'accounts.CustomUser'

# Applications installées
INSTALLED_APPS = [
    # Daphne doit être avant django.contrib.staticfiles pour Channels
    'daphne',

    # Thème admin (doit précéder django.contrib.admin)
    'jazzmin',

    # Django core
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Authentification Google (django-allauth)
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',

    # Bibliothèques tierces
    'rest_framework',
    'rest_framework_simplejwt',
    'drf_spectacular',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_htmx',
    'channels',

    # Applications GreenMove
    'core.apps.CoreConfig',
    'accounts.apps.AccountsConfig',
    'match.apps.MatchConfig',
    'tracker.apps.TrackerConfig',
    'traffic.apps.TrafficConfig',
    'planner.apps.PlannerConfig',
    'rewards.apps.RewardsConfig',
]

# Middlewares
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.locale.LocaleMiddleware',  # Gestion i18n
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django_htmx.middleware.HtmxMiddleware',      # Support Django HTMX
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.i18n',
                'core.context_processors.greenmove_context',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Configuration Base de Données
DB_ENGINE = config('DB_ENGINE', default='sqlite').lower()

if DB_ENGINE == 'postgres':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME', default='greenmove_db'),
            'USER': config('DB_USER', default='postgres'),
            'PASSWORD': config('DB_PASSWORD', default='postgres'),
            'HOST': config('DB_HOST', default='localhost'),
            'PORT': config('DB_PORT', default='5432'),
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Validation des mots de passe
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalisation
LANGUAGE_CODE = config('DEFAULT_LANGUAGE', default='fr')
TIME_ZONE = 'Africa/Tunis'
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ('fr', _('Français')),
    ('en', _('English')),
    ('ar', _('العربية')),
]

LOCALE_PATHS = [
    BASE_DIR / 'locale',
]

# Fichiers statiques et médias
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Django Channels
CHANNEL_LAYER_TYPE = config('CHANNEL_LAYER_TYPE', default='memory').lower()

if CHANNEL_LAYER_TYPE == 'redis':
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels_redis.core.RedisChannelLayer',
            'CONFIG': {
                'hosts': [config('REDIS_URL', default='redis://127.0.0.1:6379/0')],
            },
        },
    }
else:
    CHANNEL_LAYERS = {
        'default': {
            'BACKEND': 'channels.layers.InMemoryChannelLayer',
        },
    }

# Crispy Forms
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ),
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
    },
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
}

# DRF Spectacular (OpenAPI 3 / Swagger)
SPECTACULAR_SETTINGS = {
    'TITLE': 'GreenMove API - Mobilité Durable avec IA',
    'DESCRIPTION': 'Documentation interactive de l\'API REST de GreenMove (Tunis Hackathon 2026).',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Redirections d'authentification
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'match:search'
LOGOUT_REDIRECT_URL = 'core:home'

# Configuration du cache pour Nominatim & requêtes externes
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'greenmove-cache',
        'TIMEOUT': 3600,  # 1 heure par défaut
    }
}

# Paramètres personnalisés APIs GreenMove
NOMINATIM_USER_AGENT = config('NOMINATIM_USER_AGENT', default='GreenMove-Platform/1.0 (contact@greenmove.tn)')
ORS_API_KEY = config('ORS_API_KEY', default='')
OPEN_METEO_API_URL = config('OPEN_METEO_API_URL', default='https://api.open-meteo.com/v1/forecast')

# Notifications Telegram Bot (gratuites) — no-op si token vide
TELEGRAM_BOT_TOKEN = config('TELEGRAM_BOT_TOKEN', default='')
TELEGRAM_CHAT_ID = config('TELEGRAM_CHAT_ID', default='')

# ==========================================
# Authentification Google (django-allauth)
# ==========================================
SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]
GOOGLE_CLIENT_ID = config('GOOGLE_CLIENT_ID', default='')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default='')
GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
        **({'APP': {'client_id': GOOGLE_CLIENT_ID, 'secret': GOOGLE_CLIENT_SECRET, 'key': ''}}
           if GOOGLE_LOGIN_ENABLED else {}),
    }
}
ACCOUNT_LOGIN_METHODS = {'username', 'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'username*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'none'
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True

# ==========================================
# E-mail, Celery (Beat) et IA optionnelle
# ==========================================
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='GreenMove <noreply@greenmove.tn>')
CELERY_BROKER_URL = config('CELERY_BROKER_URL', default=config('REDIS_URL', default='redis://127.0.0.1:6379/0'))
# Sans broker (dev/tests), les tâches s'exécutent de façon synchrone.
CELERY_TASK_ALWAYS_EAGER = config('CELERY_TASK_ALWAYS_EAGER', default=False, cast=bool)
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'planner-month-end-projection': {
        'task': 'planner.tasks.project_month_end_all',
        'schedule': 60 * 60 * 24,  # quotidien
    },
    'planner-weekly-report': {
        'task': 'planner.tasks.send_weekly_reports',
        'schedule': 60 * 60 * 24 * 7,  # hebdomadaire
    },
}

# Explications en langage naturel : 'none' (gabarits), 'gemini' ou 'ollama'. Repli automatique sur les gabarits.
LLM_PROVIDER = config('LLM_PROVIDER', default='none').lower()
GEMINI_API_KEY = config('GEMINI_API_KEY', default='')
GEMINI_MODEL = config('GEMINI_MODEL', default='gemini-1.5-flash')
OLLAMA_URL = config('OLLAMA_URL', default='http://127.0.0.1:11434')
OLLAMA_MODEL = config('OLLAMA_MODEL', default='llama3')

# ==========================================
# Thème d'administration (Jazzmin) aux couleurs GreenMove
# ==========================================
JAZZMIN_SETTINGS = {
    'site_title': 'GreenMove Admin',
    'site_header': 'GreenMove',
    'site_brand': 'GreenMove',
    'welcome_sign': 'Administration GreenMove - Mobilité verte',
    'copyright': 'GreenMove 2026',
    'search_model': ['accounts.CustomUser'],
    'topmenu_links': [
        {'name': 'Site', 'url': '/', 'new_window': True},
        {'name': 'API Docs', 'url': '/api/docs/', 'new_window': True},
    ],
    'icons': {
        'accounts.CustomUser': 'fas fa-user-circle',
        'accounts.AuditLog': 'fas fa-clipboard-list',
        'planner.TripRecord': 'fas fa-route',
        'planner.RecurringTrip': 'fas fa-calendar-week',
        'planner.CarbonBudget': 'fas fa-leaf',
        'auth.Group': 'fas fa-users-cog',
    },
    'show_ui_builder': False,
}
JAZZMIN_UI_TWEAKS = {
    'navbar': 'navbar-success',
    'sidebar': 'sidebar-dark-success',
    'brand_colour': 'navbar-success',
    'accent': 'accent-success',
    'button_classes': {'primary': 'btn-success'},
}

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
