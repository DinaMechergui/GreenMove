"""Vues EcoPlanner : tableau de bord HTML + endpoints JSON + API DRF + calendrier .ics."""
import csv
import io

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.cache import cache
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework import generics, permissions, status as drf_status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import CarbonBudget, RecurringTrip, TripRecord, Mode
from .serializers import TripRecordSerializer, RecurringTripSerializer, CarbonBudgetSerializer
from .services import planning
from .services.explain import explain_plan
from .services.metrics import clustering_metrics, co2_statistics, eco_leaderboard
from .signals import GAUGE_CACHE_KEY, refresh_budget
from .tasks import (
    send_weekly_report_for, generate_explanation_async,
    generate_plan_and_report_async, REPORT_STATUS_KEY, REPORT_RESULT_KEY,
)

RAIN_WORDS = ('pluie', 'averse', 'orage', 'bruine')
EXPLANATION_CACHE_KEY = 'planner:explanation:{}'


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
    bundle = cache.get(REPORT_RESULT_KEY.format(user.pk)) if not request.GET else None
    plan = bundle['plan'] if bundle else planning.optimize_week(user, _weights(request), rain)
    # Explication : lue depuis le cache (générée par Celery), fallback immédiat sur gabarits
    explanation_key = EXPLANATION_CACHE_KEY.format(user.pk)
    explanations = cache.get(explanation_key)
    if explanations is None:
        explanations = explain_plan(plan)
        # Déclenche la régénération LLM async pour la prochaine visite
        try:
            generate_explanation_async.delay(user.pk)
        except Exception:
            pass
    recent_trips = TripRecord.objects.filter(user=user).order_by('-date')[:10]
    return render(request, 'planner/dashboard.html', {
        'plan': plan,
        'rain': rain,
        'explanations': explanations,
        'profile': planning.weekly_profile(user),
        'history': planning.weekly_history(user),
        'budget': planning.carbon_budget_status(user),
        'typology': planning.classify_user(user, get_user_model().objects.all()[:200]),
        'impact': planning.simulate_impact(user, 1, plan),
        'recurring': RecurringTrip.objects.filter(user=user),
        'weekdays': RecurringTrip.WEEKDAYS,
        'modes': Mode.choices,
        'recent_trips': recent_trips,
    })


@login_required
@require_POST
def add_trip_record(request):
    """Ajout manuel d'un trajet effectué (CRUD TripRecord)."""
    try:
        distance = float(request.POST['distance_km'])
        if distance <= 0:
            raise ValueError("La distance doit être positive.")
        TripRecord.objects.create(
            user=request.user,
            date=request.POST['date'],
            mode=request.POST['mode'],
            distance_km=distance,
            duration_min=float(request.POST.get('duration_min') or 0),
        )
        messages.success(request, "Trajet enregistré.")
    except (KeyError, ValueError) as e:
        messages.error(request, f"Formulaire invalide : {e}")
    return redirect('planner:index')


@login_required
@require_POST
def delete_trip_record(request, pk):
    """Suppression d'un trajet effectué (CRUD TripRecord)."""
    TripRecord.objects.filter(pk=pk, user=request.user).delete()
    messages.success(request, "Trajet supprimé.")
    return redirect('planner:index')


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
    """Explication LLM depuis le cache (async) ou gabarits (sync fallback)."""
    explanation_key = EXPLANATION_CACHE_KEY.format(request.user.pk)
    explanations = cache.get(explanation_key)
    if explanations is None:
        plan = planning.optimize_week(request.user, _weights(request), _rain(request))
        explanations = explain_plan(plan)
    return JsonResponse(explanations)


@login_required
def download_report(request):
    """Télécharge le rapport préparé en tâche Celery, sans bloquer la requête HTTP."""
    result = cache.get(REPORT_RESULT_KEY.format(request.user.pk))
    if not result:
        return HttpResponse("Le rapport n'est pas encore prêt. Lancez sa génération depuis le tableau de bord.",
                            status=drf_status.HTTP_202_ACCEPTED, content_type='text/plain; charset=utf-8')
    resp = HttpResponse(result['report'], content_type=result['mimetype'])
    resp['Content-Disposition'] = f"attachment; filename=greenmove_rapport.{result['extension']}"
    return resp


@login_required
@require_POST
def generate_report(request):
    """Déclenche le calcul du plan et le rendu du rapport dans Celery."""
    cache.delete(REPORT_RESULT_KEY.format(request.user.pk))
    cache.set(REPORT_STATUS_KEY.format(request.user.pk), {'state': 'queued'}, 60 * 60 * 6)
    try:
        generate_plan_and_report_async.delay(request.user.pk)
    except Exception:
        cache.set(REPORT_STATUS_KEY.format(request.user.pk), {'state': 'error'}, 60 * 60 * 6)
        messages.error(request, "Le worker Celery est indisponible; le calcul n'a pas été exécuté dans la requête web.")
        return redirect('planner:index')
    messages.info(request, "Génération du plan et du rapport placée dans Celery. Suivez l'état ci-dessous.")
    return redirect('planner:index')


@login_required
def report_status(request):
    state = cache.get(REPORT_STATUS_KEY.format(request.user.pk), {'state': 'idle'})
    return JsonResponse(state)


@login_required
@require_POST
def email_report(request):
    try:
        send_weekly_report_for.delay(request.user.pk)
        messages.success(request, "L'envoi du rapport a été placé dans la file de tâches.")
    except Exception:
        messages.error(request, "Le worker Celery est indisponible; l'envoi n'a pas été exécuté dans la requête web.")
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


# ---- Export CSV
@login_required
def export_csv(request):
    """Export CSV de tous les trajets effectués de l'utilisateur."""
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="greenmove_trajets.csv"'
    response.write('\ufeff')  # BOM UTF-8 pour Excel
    writer = csv.writer(response)
    writer.writerow(['Date', 'Mode', 'Distance (km)', 'Durée (min)', 'CO₂ (kg)'])
    for t in TripRecord.objects.filter(user=request.user).order_by('-date'):
        writer.writerow([
            t.date.strftime('%Y-%m-%d %H:%M'),
            t.get_mode_display(),
            t.distance_km,
            t.duration_min,
            t.co2_kg,
        ])
    return response


# ---- Métriques IA
@login_required
def api_metrics(request):
    """Métriques du clustering KMeans + statistiques CO₂ vs moyennes nationales."""
    return JsonResponse({
        'clustering': clustering_metrics(),
        'co2_stats': co2_statistics(request.user),
        'leaderboard': eco_leaderboard(10),
    })


@login_required
def api_leaderboard(request):
    """Classement éco du mois."""
    return JsonResponse({'leaderboard': eco_leaderboard(20)})


# ---- API DRF REST (endpoints documentés Swagger)
class TripRecordListCreateView(generics.ListCreateAPIView):
    """Liste et création des trajets effectués (CRUD complet)."""
    serializer_class = TripRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = TripRecord.objects.filter(user=self.request.user).order_by('-date')
        mode = self.request.query_params.get('mode')
        if mode:
            qs = qs.filter(mode=mode)
        return qs


class TripRecordDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail, modification et suppression d'un trajet effectué."""
    serializer_class = TripRecordSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return TripRecord.objects.filter(user=self.request.user)


class RecurringTripListCreateView(generics.ListCreateAPIView):
    """Liste et création des trajets habituels."""
    serializer_class = RecurringTripSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RecurringTrip.objects.filter(user=self.request.user)


class RecurringTripDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Détail, modification et suppression d'un trajet habituel."""
    serializer_class = RecurringTripSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return RecurringTrip.objects.filter(user=self.request.user)


class CarbonBudgetView(APIView):
    """Budget carbone du mois courant (GET = lecture, POST = mise à jour)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return JsonResponse(planning.carbon_budget_status(request.user))

    def post(self, request):
        sz = CarbonBudgetSerializer(data=request.data, context={'request': request})
        if sz.is_valid():
            start = timezone.localdate().replace(day=1)
            obj, _ = CarbonBudget.objects.update_or_create(
                user=request.user, month=start, defaults={'budget_kg': sz.validated_data['budget_kg']})
            refresh_budget(request.user, notify=False)
            return Response(CarbonBudgetSerializer(obj).data)
        return Response(sz.errors, status=drf_status.HTTP_400_BAD_REQUEST)


class EcoMetricsAPIView(APIView):
    """Métriques IA : qualité du clustering KMeans + comparaison CO₂ nationale (Swagger documenté)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response({
            'clustering': clustering_metrics(),
            'co2_stats': co2_statistics(request.user),
        })


class EcoLeaderboardAPIView(APIView):
    """Classement éco-mobilité du mois (top utilisateurs bas-carbone)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            limit = min(int(request.query_params.get('limit', 10)), 50)
        except ValueError:
            limit = 10
        return Response({'leaderboard': eco_leaderboard(limit)})
