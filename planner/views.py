"""Vues EcoPlanner : tableau de bord HTML + endpoints JSON + calendrier .ics."""
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import CarbonBudget, RecurringTrip
from .services import planning
from .services.explain import explain_plan
from .services.report import render_report
from .signals import GAUGE_CACHE_KEY, refresh_budget
from .tasks import send_weekly_report_for

RAIN_WORDS = ('pluie', 'averse', 'orage', 'bruine')


def _weights(request):
    out = {}
    for key in ('co2', 'time', 'cost', 'comfort'):
        try:
            out[key] = max(0.0, float(request.GET[key]))
        except (KeyError, ValueError):
            continue
    return out or None


def _rain(request):
    """?rain=1/0 force la météo ; sinon on lit le service météo (Open-Meteo, avec repli)."""
    forced = request.GET.get('rain')
    if forced:
        return forced in ('1', 'true', 'on')
    try:
        from core.services.weather import get_tunis_weather
        w = get_tunis_weather()
        return (not w.get('is_fallback')) and any(k in str(w.get('description', '')).lower() for k in RAIN_WORDS)
    except Exception:
        return False


@login_required
def dashboard(request):
    user = request.user
    rain = _rain(request)
    plan = planning.optimize_week(user, _weights(request), rain)
    return render(request, 'planner/dashboard.html', {
        'plan': plan,
        'rain': rain,
        'explanations': explain_plan(plan),
        'profile': planning.weekly_profile(user),
        'history': planning.weekly_history(user),
        'budget': planning.carbon_budget_status(user),
        'typology': planning.classify_user(user, get_user_model().objects.all()[:200]),
        'impact': planning.simulate_impact(user, 1, plan),
        'recurring': RecurringTrip.objects.filter(user=user),
        'weekdays': RecurringTrip.WEEKDAYS,
    })


@login_required
@require_POST
def add_recurring(request):
    try:
        RecurringTrip.objects.create(
            user=request.user, label=request.POST['label'][:100], weekday=int(request.POST['weekday']),
            arrival_time=request.POST['arrival_time'], distance_km=float(request.POST['distance_km']),
        )
        messages.success(request, "Trajet habituel ajouté.")
    except (KeyError, ValueError):
        messages.error(request, "Formulaire invalide.")
    return redirect('planner:index')


@login_required
@require_POST
def delete_recurring(request, pk):
    RecurringTrip.objects.filter(pk=pk, user=request.user).delete()
    return redirect('planner:index')


@login_required
@require_POST
def set_budget(request):
    try:
        value = float(request.POST['budget_kg'])
        if value <= 0:
            raise ValueError
        start = timezone.localdate().replace(day=1)
        CarbonBudget.objects.update_or_create(user=request.user, month=start, defaults={'budget_kg': value})
        refresh_budget(request.user, notify=False)
    except (KeyError, ValueError):
        messages.error(request, "Budget invalide.")
    return redirect('planner:index')


# ---- JSON (Chart.js / intégrations)
@login_required
def api_habits(request):
    return JsonResponse({'profile': planning.weekly_profile(request.user),
                         'weekly': planning.weekly_history(request.user)})


@login_required
def api_plan(request):
    return JsonResponse(planning.optimize_week(request.user, _weights(request), _rain(request)))


@login_required
def api_budget(request):
    """Jauge en temps réel : lue dans le cache alimenté par le signal post_save de TripRecord."""
    status = cache.get(GAUGE_CACHE_KEY.format(request.user.pk)) or refresh_budget(request.user, notify=False)
    return JsonResponse(status)


@login_required
def api_explain(request):
    plan = planning.optimize_week(request.user, _weights(request), _rain(request))
    return JsonResponse(explain_plan(plan))


@login_required
def download_report(request):
    """Rapport hebdomadaire (PDF si WeasyPrint est disponible, sinon HTML)."""
    content, mimetype, ext = render_report(request.user)
    resp = HttpResponse(content, content_type=mimetype)
    resp['Content-Disposition'] = f'attachment; filename="greenmove_rapport.{ext}"'
    return resp


@login_required
@require_POST
def email_report(request):
    send_weekly_report_for.delay(request.user.pk)
    messages.success(request, "Rapport envoyé par e-mail.")
    return redirect('planner:index')


@login_required
def api_simulate(request):
    try:
        years = min(max(int(request.GET.get('years', 1)), 1), 10)
    except ValueError:
        years = 1
    return JsonResponse(planning.simulate_impact(request.user, years))


# ---- Calendrier
@login_required
def export_calendar(request):
    resp = HttpResponse(planning.export_ics(request.user), content_type='text/calendar; charset=utf-8')
    resp['Content-Disposition'] = 'attachment; filename="greenmove_plan.ics"'
    return resp


@login_required
@require_POST
def import_calendar(request):
    upload = request.FILES.get('ics')
    if not upload or upload.size > 1_000_000:
        messages.error(request, "Fichier .ics manquant ou trop volumineux.")
    else:
        n = planning.import_ics(request.user, upload.read().decode('utf-8', errors='ignore'))
        messages.success(request, f"{n} évènement(s) importé(s).")
    return redirect('planner:index')
