"""
Context Processors pour le projet GreenMove.
Fournit des variables globales à l'ensemble des templates.
"""
from django.conf import settings
from django.utils.translation import get_language
from datetime import datetime

def greenmove_context(request):
    """
    Injecte des données de contexte réutilisables dans tous les gabarits :
    - Direction du texte (RTL pour l'arabe, LTR pour le français et l'anglais)
    - Langue actuelle
    - Année courante
    - Nom et slogan de la plateforme
    """
    lang = get_language() or 'fr'
    is_rtl = lang.startswith('ar')

    return {
        'CURRENT_LANGUAGE': lang,
        'GOOGLE_LOGIN_ENABLED': getattr(settings, 'GOOGLE_LOGIN_ENABLED', False),
        'IS_RTL': is_rtl,
        'CURRENT_YEAR': datetime.now().year,
        'PLATFORM_NAME': 'GreenMove',
        'PLATFORM_TAGLINE': 'Mobilité durable & IA pour le Grand Tunis',
        'HACKATHON_BADGE': 'Hackathon IA & Climat 2026',
    }
