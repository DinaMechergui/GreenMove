"""Analyse des habitudes, plan optimisé, typologie, budget carbone, simulateur et export .ics.

Tout est en Python/ORM pur (pas de dépendance lourde) :
- habitudes : annotate / TruncWeek / Window(Lag)
- plan : minimisation d'un score pondéré CO2 / temps / coût / confort météo (énumération exacte,
  équivalent à un solveur car les choix par trajet sont indépendants)
- typologie : KMeans implémenté localement (déterministe)
"""
import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta

from django.db.models import Count, F, Sum, Window
from django.db.models.functions import ExtractHour, Lag, TruncWeek, ExtractWeekDay
from django.utils import timezone

from ..models import CarbonBudget, Mode, RecurringTrip, TripRecord
from .emissions import (BASE_COMFORT, COST_TND_KM, EMISSION_FACTORS, KG_CO2_PER_TREE_YEAR,
                        SPEED_KMH, co2_kg)

MODE_LABELS = dict(Mode.choices)
# Garde-fous de faisabilité (km)
MAX_DISTANCE = {'WALK': 4.0, 'BIKE': 15.0}
DEFAULT_WEIGHTS = {'co2': 0.4, 'time': 0.25, 'cost': 0.15, 'comfort': 0.2}


# --------------------------------------------------------------------------- habitudes
def weekly_history(user, weeks=8):
    """CO2 par semaine avec variation vs semaine précédente (fonction de fenêtre Lag)."""
    since = timezone.now() - timedelta(weeks=weeks)
    qs = (TripRecord.objects.filter(user=user, date__gte=since)
          .annotate(week=TruncWeek('date')).values('week')
          .annotate(co2=Sum('co2_kg'), km=Sum('distance_km'), trips=Count('id'))
          .annotate(prev_co2=Window(expression=Lag('co2'), order_by=F('week').asc()))
          .order_by('week'))
    rows = []
    for r in qs:
        prev = r['prev_co2']
        rows.append({
            'week': r['week'].date().isoformat(), 'co2_kg': round(r['co2'] or 0, 2),
            'km': round(r['km'] or 0, 1), 'trips': r['trips'],
            'delta_pct': round((r['co2'] - prev) / prev * 100, 1) if prev else None,
        })
    return rows


def weekly_profile(user, weeks=8):
    """Profil hebdomadaire : modes, heures de pointe, CO2 par jour de semaine (lundi=0)."""
    since = timezone.now() - timedelta(weeks=weeks)
    base = TripRecord.objects.filter(user=user, date__gte=since)
    modes = {
        r['mode']: {'trips': r['n'], 'km': round(r['km'], 1), 'co2_kg': round(r['co2'], 2)}
        for r in base.values('mode').annotate(n=Count('id'), km=Sum('distance_km'), co2=Sum('co2_kg'))
    }
    peak = list(base.annotate(h=ExtractHour('date')).values('h')
                .annotate(n=Count('id')).order_by('-n', 'h')[:3])
    # ExtractWeekDay : 1=dimanche..7=samedi -> on ramène à lundi=0
    per_day = defaultdict(float)
    for r in base.annotate(d=ExtractWeekDay('date')).values('d').annotate(co2=Sum('co2_kg')):
        per_day[(r['d'] + 5) % 7] = round(r['co2'] or 0, 2)
    return {
        'modes': modes,
        'peak_hours': [{'hour': p['h'], 'trips': p['n']} for p in peak],
        'co2_by_weekday': [per_day.get(i, 0.0) for i in range(7)],
        'total_co2_kg': round(sum(m['co2_kg'] for m in modes.values()), 2),
    }


# --------------------------------------------------------------------------- plan optimisé
def score_options(distance_km, weights=None, bad_weather=False, car_available=True, preferred_mode=''):
    """Évalue chaque mode ; retourne la liste triée par score (plus bas = meilleur)."""
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    options = []
    for mode in Mode.values:
        if mode in MAX_DISTANCE and distance_km > MAX_DISTANCE[mode]:
            continue
        if mode == 'CAR' and not car_available:
            continue
        minutes = distance_km / SPEED_KMH[mode] * 60 + (5 if mode in ('BUS', 'METRO') else 0)
        comfort = BASE_COMFORT[mode]
        if bad_weather and mode in ('WALK', 'BIKE'):
            comfort -= 0.45
        if preferred_mode and mode == preferred_mode:
            comfort += 0.15  # le mode préféré du profil est légèrement favorisé
        options.append({
            'mode': mode, 'label': str(MODE_LABELS[mode]), 'minutes': round(minutes),
            'co2_kg': co2_kg(mode, distance_km), 'cost_tnd': round(COST_TND_KM[mode] * distance_km, 2),
            'comfort': round(max(comfort, 0.05), 2),
        })
    max_co2 = max(o['co2_kg'] for o in options) or 1
    max_min = max(o['minutes'] for o in options) or 1
    max_cost = max(o['cost_tnd'] for o in options) or 1
    for o in options:
        o['score'] = round(w['co2'] * o['co2_kg'] / max_co2 + w['time'] * o['minutes'] / max_min
                           + w['cost'] * o['cost_tnd'] / max_cost + w['comfort'] * (1 - o['comfort']), 4)
    return sorted(options, key=lambda o: o['score'])


def _profile(user):
    from accounts.models import Profile
    return Profile.objects.get_or_create(user=user)[0]


def _solve(options_per_trip, weekly_cap_kg):
    """Minimise le score total sous un plafond hebdomadaire de CO2 (OR-Tools CP-SAT).

    Retourne (indices choisis, solveur utilisé, plafond respecté). Repli glouton si OR-Tools est absent ou
    si le plafond est irréalisable (le plafond est alors ignoré et signalé).
    """
    greedy = [0] * len(options_per_trip)  # options triées : indice 0 = meilleur score
    if not options_per_trip:
        return greedy, 'none', True
    try:
        from ortools.sat.python import cp_model
    except ImportError:
        total = sum(o[0]['co2_kg'] for o in options_per_trip)
        return greedy, 'greedy', total <= weekly_cap_kg
    model = cp_model.CpModel()
    x = [[model.NewBoolVar(f'x{i}_{j}') for j in range(len(opts))] for i, opts in enumerate(options_per_trip)]
    for row in x:
        model.AddExactlyOne(row)
    scale_s, scale_c = 10000, 1000
    total_co2 = sum(int(round(o['co2_kg'] * scale_c)) * x[i][j]
                    for i, opts in enumerate(options_per_trip) for j, o in enumerate(opts))
    min_possible = sum(min(int(round(o['co2_kg'] * scale_c)) for o in opts) for opts in options_per_trip)
    cap = int(round(weekly_cap_kg * scale_c))
    binding = min_possible <= cap
    if binding:
        model.Add(total_co2 <= cap)
    model.Minimize(sum(int(round(o['score'] * scale_s)) * x[i][j]
                       for i, opts in enumerate(options_per_trip) for j, o in enumerate(opts)))
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 2.0
    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return greedy, 'greedy', False
    chosen = [next(j for j in range(len(opts)) if solver.BooleanValue(x[i][j]))
              for i, opts in enumerate(options_per_trip)]
    return chosen, 'ortools', binding


def optimize_week(user, weights=None, bad_weather=False):
    """Plan de semaine : mode par trajet minimisant un score pondéré CO2/temps/coût/confort,
    sous la contrainte du budget carbone hebdomadaire (budget mensuel du profil x 7/30)."""
    car_ok = user.vehicle_type != user.VehicleChoices.NONE
    profile = _profile(user)
    budget = CarbonBudget.objects.filter(user=user, month=timezone.localdate().replace(day=1)).first()
    monthly_kg = budget.budget_kg if budget else profile.carbon_goal_kg
    weekly_cap = monthly_kg * 7 / 30
    trips = list(RecurringTrip.objects.filter(user=user))
    all_options = [score_options(t.distance_km, weights, bad_weather, car_available=car_ok,
                                 preferred_mode=profile.preferred_mode) for t in trips]
    chosen, solver_name, cap_ok = _solve(all_options, weekly_cap)
    plan, total_co2, baseline_co2 = [], 0.0, 0.0
    for trip, options, idx in zip(trips, all_options, chosen):
        best = options[idx]
        others = [o for k, o in enumerate(options) if k != idx]
        leave = (datetime.combine(date.today(), trip.arrival_time)
                 - timedelta(minutes=best['minutes'] + 5)).time()
        car_co2 = co2_kg('CAR', trip.distance_km)
        total_co2 += best['co2_kg']
        baseline_co2 += car_co2
        plan.append({
            'id': trip.id, 'label': trip.label, 'weekday': trip.weekday,
            'weekday_label': str(trip.get_weekday_display()),
            'arrival': trip.arrival_time.strftime('%H:%M'), 'leave_at': leave.strftime('%H:%M'),
            'distance_km': trip.distance_km, 'best': best, 'alternatives': others[:2],
            'co2_saved_kg': round(car_co2 - best['co2_kg'], 3),
        })
    return {
        'plan': plan, 'total_co2_kg': round(total_co2, 2), 'baseline_car_co2_kg': round(baseline_co2, 2),
        'co2_saved_kg': round(baseline_co2 - total_co2, 2), 'weights': {**DEFAULT_WEIGHTS, **(weights or {})},
        'has_vehicle': car_ok, 'solver': solver_name, 'weekly_cap_kg': round(weekly_cap, 2),
        'cap_respected': cap_ok and total_co2 <= weekly_cap + 1e-9,
    }


# --------------------------------------------------------------------------- typologie KMeans
def _kmeans(points, k):
    """KMeans scikit-learn (déterministe) ; repli sur l'implémentation Python si indisponible."""
    try:
        from sklearn.cluster import KMeans
    except ImportError:
        return _kmeans_py(points, k)
    k = min(k, len(points))
    model = KMeans(n_clusters=k, n_init=10, random_state=0).fit(points)
    return [int(l) for l in model.labels_], [list(c) for c in model.cluster_centers_]


def _kmeans_py(points, k, iters=50):
    """KMeans déterministe (init : points espacés après tri) sur des vecteurs de même taille."""
    k = min(k, len(points))
    order = sorted(range(len(points)), key=lambda i: sum(points[i]))
    centers = [list(points[order[int(i * (len(points) - 1) / max(k - 1, 1))]]) for i in range(k)]
    labels = [0] * len(points)
    for _ in range(iters):
        new = [min(range(k), key=lambda c: sum((a - b) ** 2 for a, b in zip(p, centers[c]))) for p in points]
        if new == labels and _ > 0:
            break
        labels = new
        for c in range(k):
            members = [p for p, l in zip(points, labels) if l == c]
            if members:
                centers[c] = [sum(col) / len(members) for col in zip(*members)]
    return labels, centers


def user_features(user, weeks=8):
    """(part voiture, part mobilité douce+TC, km/semaine) normalisés pour le clustering."""
    since = timezone.now() - timedelta(weeks=weeks)
    rows = TripRecord.objects.filter(user=user, date__gte=since).values('mode').annotate(km=Sum('distance_km'))
    km = {r['mode']: r['km'] or 0 for r in rows}
    total = sum(km.values())
    if not total:
        return None
    car = km.get('CAR', 0) / total
    soft = (km.get('WALK', 0) + km.get('BIKE', 0)) / total
    return [car, soft, min(total / weeks / 100, 1)]


TYPOLOGY = {
    'driver': {'label': 'Conducteur', 'goal_factor': 0.9,
               'advice': "Objectif progressif : -10 % de CO2 par mois, commencez par 1 trajet en bus/métro."},
    'mixed': {'label': 'Mixte', 'goal_factor': 0.8,
              'advice': "Objectif : remplacer vos trajets voiture < 5 km par vélo ou transport en commun."},
    'soft': {'label': 'Mobilité douce', 'goal_factor': 0.95,
             'advice': "Excellent ! Maintenez votre rythme et partagez vos trajets longs en covoiturage."},
}


def classify_user(user, population_users=None, k=3):
    """Classe l'utilisateur via KMeans sur la population (fallback sur règles si peu de données)."""
    me = user_features(user)
    if me is None:
        return {'type': 'mixed', **TYPOLOGY['mixed'], 'method': 'default'}
    others = [(u, f) for u in (population_users or []) if (f := user_features(u)) is not None and u != user]
    points = [me] + [f for _, f in others]
    if len(points) >= k:
        labels, centers = _kmeans(points, k)
        # Nomme chaque cluster d'après son centre : voiture élevée -> conducteur, mobilité douce -> soft
        names = {}
        for c, center in enumerate(centers):
            names[c] = 'driver' if center[0] >= 0.55 else 'soft' if center[1] >= 0.5 else 'mixed'
        kind, method = names[labels[0]], 'kmeans'
    else:
        kind = 'driver' if me[0] >= 0.55 else 'soft' if me[1] >= 0.5 else 'mixed'
        method = 'rules'
    # Objectif progressif : consommation des 30 derniers jours x facteur du groupe
    recent = TripRecord.objects.filter(user=user, date__gte=timezone.now() - timedelta(days=30)) \
        .aggregate(s=Sum('co2_kg'))['s'] or 0
    suggested = round(recent * TYPOLOGY[kind]['goal_factor'], 1) if recent else None
    return {'type': kind, **TYPOLOGY[kind], 'method': method, 'suggested_goal_kg': suggested}


# --------------------------------------------------------------------------- budget carbone
def _month_bounds(day):
    start = day.replace(day=1)
    return start, day.replace(day=calendar.monthrange(day.year, day.month)[1])


def carbon_budget_status(user, today=None):
    today = today or timezone.localdate()
    start, end = _month_bounds(today)
    budget = CarbonBudget.objects.filter(user=user, month=start).first()
    budget_kg = budget.budget_kg if budget else _profile(user).carbon_goal_kg
    used = TripRecord.objects.filter(user=user, date__date__gte=start, date__date__lte=today) \
        .aggregate(s=Sum('co2_kg'))['s'] or 0
    elapsed = max((today - start).days + 1, 1)
    days_in_month = end.day
    projection = used / elapsed * days_in_month
    return {
        'month': start.isoformat(), 'budget_kg': budget_kg, 'used_kg': round(used, 2),
        'remaining_kg': round(budget_kg - used, 2), 'used_pct': round(used / budget_kg * 100, 1) if budget_kg else 0,
        'projected_kg': round(projection, 2), 'will_exceed': projection > budget_kg,
    }


# --------------------------------------------------------------------------- simulateur
def simulate_impact(user, years=1, plan_result=None):
    """« Si vous suivez ce plan N an(s) : X kg CO2, Y TND, Z arbres. »"""
    plan_result = plan_result or optimize_week(user)
    per_week_saved = plan_result['co2_saved_kg']
    saved = per_week_saved * 52 * years
    money = 0.0
    for item in plan_result['plan']:
        car_cost = COST_TND_KM['CAR'] * item['distance_km']
        money += car_cost - item['best']['cost_tnd']
    money *= 52 * years
    return {
        'years': years, 'co2_saved_kg': round(saved, 1), 'money_saved_tnd': round(money, 1),
        'trees_equivalent': round(saved / KG_CO2_PER_TREE_YEAR, 1),
        'chart': {'labels': [f"M{m}" for m in range(1, 12 * years + 1)],
                  'data': [round(per_week_saved * 52 / 12 * m, 1) for m in range(1, 12 * years + 1)]},
    }


# --------------------------------------------------------------------------- calendrier .ics (icalendar)
def export_ics(user, plan_result=None, start_monday=None):
    """Génère un .ics : un évènement par trajet planifié + rappel « partez maintenant »."""
    from icalendar import Alarm, Calendar, Event
    plan_result = plan_result or optimize_week(user)
    today = timezone.localdate()
    monday = start_monday or today - timedelta(days=today.weekday())
    cal = Calendar()
    cal.add('prodid', '-//GreenMove//EcoPlanner//FR')
    cal.add('version', '2.0')
    for item in plan_result['plan']:
        day = monday + timedelta(days=item['weekday'])
        end = datetime.combine(day, datetime.strptime(item['arrival'], '%H:%M').time())
        start = end - timedelta(minutes=item['best']['minutes'])
        ev = Event()
        ev.add('uid', f"greenmove-{user.pk}-{item['id']}-{day.isoformat()}@greenmove.tn")
        ev.add('dtstamp', timezone.now())
        ev.add('dtstart', start)
        ev.add('dtend', end)
        ev.add('summary', f"{item['label']} ({item['best']['label']})")
        ev.add('description', f"CO2 : {item['best']['co2_kg']} kg - GreenMove")
        ev.add('x-greenmove-distance-km', str(item['distance_km']))
        alarm = Alarm()
        alarm.add('action', 'DISPLAY')
        alarm.add('description', 'Partez maintenant !')
        alarm.add('trigger', timedelta(0))
        ev.add_component(alarm)
        cal.add_component(ev)
    return cal.to_ical().decode('utf-8')


def import_ics(user, text, default_distance_km=5.0):
    """Importe les évènements d'un .ics comme trajets habituels (distance : X-GREENMOVE-DISTANCE-KM sinon défaut)."""
    from icalendar import Calendar
    try:
        cal = Calendar.from_ical(text)
    except ValueError:
        return 0
    created = 0
    for ev in cal.walk('VEVENT'):
        start = ev.get('dtstart')
        if start is None:
            continue
        start = start.dt
        if not isinstance(start, datetime):  # évènement « journée entière » : pas d'heure d'arrivée
            continue
        try:
            distance = float(str(ev.get('x-greenmove-distance-km', default_distance_km)))
        except ValueError:
            distance = default_distance_km
        RecurringTrip.objects.create(
            user=user, label=str(ev.get('summary', 'Évènement'))[:100], weekday=start.weekday(),
            arrival_time=start.time(), distance_km=distance)
        created += 1
    return created
