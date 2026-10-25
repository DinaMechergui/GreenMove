"""Explications en langage naturel : gabarits par défaut, enrichissement LLM optionnel.

Le projet fonctionne sans LLM : en cas d'absence de configuration, d'erreur réseau ou de
réponse vide, on retombe toujours sur les gabarits.
"""
import logging

import requests
from django.conf import settings
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


def template_explanation(item):
    """Gabarit traduisible pour un trajet du plan."""
    best = item['best']
    text = _("%(day)s : prenez %(mode)s pour « %(label)s » (%(min)s min, %(co2)s kg de CO₂, %(cost)s TND). "
             "Partez à %(leave)s pour arriver à %(arrival)s.") % {
        'day': item['weekday_label'], 'mode': best['label'].lower(), 'label': item['label'],
        'min': best['minutes'], 'co2': best['co2_kg'], 'cost': best['cost_tnd'],
        'leave': item['leave_at'], 'arrival': item['arrival'],
    }
    if item['co2_saved_kg'] > 0:
        text += ' ' + _("Vous évitez %(kg)s kg de CO₂ par rapport à la voiture.") % {'kg': item['co2_saved_kg']}
    return text


def _llm(prompt):
    provider = getattr(settings, 'LLM_PROVIDER', 'none')
    try:
        if provider == 'gemini' and settings.GEMINI_API_KEY:
            url = ('https://generativelanguage.googleapis.com/v1beta/models/'
                   f'{settings.GEMINI_MODEL}:generateContent')
            r = requests.post(url, params={'key': settings.GEMINI_API_KEY}, timeout=8,
                              json={'contents': [{'parts': [{'text': prompt}]}]})
            r.raise_for_status()
            return r.json()['candidates'][0]['content']['parts'][0]['text'].strip()
        if provider == 'ollama':
            r = requests.post(f'{settings.OLLAMA_URL}/api/generate', timeout=15,
                              json={'model': settings.OLLAMA_MODEL, 'prompt': prompt, 'stream': False})
            r.raise_for_status()
            return r.json().get('response', '').strip()
    except Exception as exc:  # repli silencieux sur les gabarits
        logger.warning("LLM indisponible (%s) : repli sur les gabarits", exc)
    return ''


def explain_plan(plan_result):
    """Retourne {'items': [...], 'summary': str, 'source': 'template'|'llm'}."""
    items = [template_explanation(i) for i in plan_result['plan']]
    summary = _("Votre plan évite %(kg)s kg de CO₂ cette semaine par rapport à un usage exclusif de la voiture.") % {
        'kg': plan_result['co2_saved_kg']}
    enriched = _llm("Reformule en 2 phrases motivantes, sans inventer de chiffres : " + summary + ' ' + ' '.join(items)) \
        if items else ''
    return {'items': items, 'summary': enriched or summary, 'source': 'llm' if enriched else 'template'}
