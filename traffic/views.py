import json
import logging
from datetime import timedelta

from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time
from django.utils.translation import gettext as _

from traffic.api.params import ParamError, parse_best_time
from traffic.best_time import best_departure
from traffic.ml.predict import ModelNotTrained
from traffic.models import MonitoringPoint

logger = logging.getLogger(__name__)


def coming_soon(request):
    """Vue 'Bientôt disponible' pour le module Traffic Eco-Prédictif."""
    return render(request, 'placeholder.html', {
        'module_title': 'Traffic Eco-Prédictif',
        'module_icon': 'bi-stoplights',
        'module_description': 'Anticipation des embouteillages du Grand Tunis, prédiction des zones de ralentissement et calcul d\'itinéraires alternatifs à faible émission de gaz à effet de serre.',
        'developer_name': 'Équipe IA & Données Urbaines',
        'eta': 'Hackathon Étape Suivante',
    })


def _active_points():
    return MonitoringPoint.objects.filter(is_active=True).order_by('name')


def _level_strings():
    return {'fluide': _('Fluide'), 'modere': _('Modéré'), 'dense': _('Dense'), 'bloque': _('Bloqué')}


# ---------------------------------------------------------------- Page 1 : carte
def traffic_map(request):
    """Carte de congestion prévue (données chargées en JS depuis l'API)."""
    return render(request, 'traffic/map.html', {
        'page_title': _('Carte de congestion prévue'),
        'page_intro': _("Prévision du trafic sur les points clés du Grand Tunis, par pas de 15 minutes."),
        'points': _active_points(),
        'today': timezone.localdate().isoformat(),
        'js_strings': {
            'levels': _level_strings(),
            'loading': _('Chargement de la prévision…'),
            'forecastFor': _('Prévision pour le {date} à {time}.'),
            'summary': _('{n} points : {fluide} fluides, {modere} modérés, {dense} denses, {bloque} bloqués.'),
            'congestion': _('Congestion'),
            'level': _('Niveau'),
            'error': _('Impossible de charger la prévision.'),
            'noRain': _('Aucune'),
            'unavailable': _('Indisponible'),
            'markerLabel': _('{name} : congestion {pct} %, niveau {level}'),
            'rainUsed': _('Pluie prise en compte : {mm} mm.'),
        },
    })


# ---------------------------------------------------- Page 2 : meilleur moment
def compute_best_time(params):
    """Valide le formulaire et appelle best_departure. Retourne un contexte de template."""
    day = parse_date(params.get('day') or '')
    start_t = parse_time(params.get('start_time') or '')
    end_t = parse_time(params.get('end_time') or '')
    if not day:
        return {'error': _('Veuillez choisir un jour valide.')}
    if not start_t or not end_t:
        return {'error': _('Veuillez indiquer une heure de début et une heure de fin valides.')}
    api_params = {
        'origin': params.get('origin'), 'destination': params.get('destination'),
        'start': f'{day.isoformat()}T{start_t:%H:%M}', 'end': f'{day.isoformat()}T{end_t:%H:%M}',
        'step': params.get('step') or '15',
    }
    try:
        origin, dest, start, end, step = parse_best_time(api_params)
        result = best_departure(origin.id, dest.id, start, end, step)
    except ParamError as exc:
        return {'error': exc.message}
    except ModelNotTrained:
        return {'error': _("Modèle non entraîné : l'administrateur doit lancer « python manage.py train_traffic_model »."),
                'error_kind': 'model'}
    except Exception:  # noqa: BLE001 - on ne montre jamais une trace technique à l'utilisateur
        logger.exception('Erreur best_departure')
        return {'error': _('Le calcul a échoué. Réessayez dans quelques instants.')}

    options = result['options']
    best_index = options.index(result['best'])
    return {
        'result': result,
        'chart_data': {
            'labels': [o['departure'][11:] for o in options],
            'durations': [o['duration_min'] for o in options],
            'congestion': [round(o['congestion'] * 100) for o in options],
            'bestIndex': best_index,
            'worstIndex': options.index(result['worst']),
            'strings': {'duration': _('Durée du trajet (min)'), 'best': _('Meilleur créneau'),
                        'departure': _('Heure de départ'), 'minutes': _('minutes')},
        },
    }


def best_time(request):
    """Requête HTMX : fragment de résultat seul. Sans JS : page complète avec résultat."""
    submitted = 'origin' in request.GET
    result_ctx = compute_best_time(request.GET) if submitted else {}

    if getattr(request, 'htmx', False):
        return render(request, 'traffic/partials/best_time_result.html', result_ctx)

    tomorrow = timezone.localdate() + timedelta(days=1)
    points = list(_active_points())
    points_json = json.dumps({
        str(p.id): {
            'id': str(p.id),
            'name': p.name,
            'lat': float(p.latitude),
            'lon': float(p.longitude),
        }
        for p in points
    })
    return render(request, 'traffic/best_time.html', {
        'page_title': _('Meilleur moment pour partir'),
        'page_intro': _("Comparez les heures de départ et gagnez du temps grâce à la prévision du trafic."),
        'points': points,
        'points_json': points_json,
        'form': {
            'origin': request.GET.get('origin', ''),
            'destination': request.GET.get('destination', ''),
            'day': request.GET.get('day', tomorrow.isoformat()),
            'start_time': request.GET.get('start_time', '07:00'),
            'end_time': request.GET.get('end_time', '10:00'),
        },
        'submitted': submitted,
        **result_ctx,
    })


# ------------------------------------------------------- Page 3 : historique
def history(request):
    """Historique d'un point : congestion enregistrée vs prévision du modèle."""
    return render(request, 'traffic/history.html', {
        'page_title': _("Historique d'un point"),
        'page_intro': _("Congestion enregistrée comparée à la prévision du modèle."),
        'points': _active_points(),
        'js_strings': {
            'real': _('Congestion enregistrée (%)'),
            'predicted': _('Prévision du modèle (%)'),
            'loading': _("Chargement de l'historique…"),
            'error': _("Impossible de charger l'historique."),
            'empty': _('Aucune donnée enregistrée pour ce point.'),
            'summary': _('{n} mesures. Congestion moyenne : {avg} %, maximum : {max} %.'),
            'mae': _('Écart moyen entre le modèle et les mesures : {mae} points de pourcentage.'),
            'noModel': _('Modèle non entraîné : la prévision n\'est pas affichée.'),
        },
    })


# ------------------------------------------------------------ À propos
def about_data(request):
    """Transparence : origine des données de trafic et de météo."""
    return render(request, 'traffic/about_data.html', {
        'page_title': _('À propos des données'),
        'page_intro': _("D'où viennent les chiffres affichés dans le module Traffic."),
        'traffic_source': settings.TRAFFIC_SOURCE,
        'points': _active_points(),
    })
