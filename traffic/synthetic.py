import math
import random

# Poids des pics par profil : matin (8h), midi (13h), soir (17h30)
WEIGHTS = {
    'am_heavy': {'am': 0.65, 'mid': 0.15, 'pm': 0.40},
    'pm_heavy': {'am': 0.40, 'mid': 0.15, 'pm': 0.65},
    'center':   {'am': 0.50, 'mid': 0.25, 'pm': 0.55},
    'highway':  {'am': 0.70, 'mid': 0.15, 'pm': 0.70},
}
FREE_FLOW = {'am_heavy': 50, 'pm_heavy': 50, 'center': 40, 'highway': 90}


def _peak(hour, center, width):
    return math.exp(-((hour - center) ** 2) / (2 * width ** 2))


def synthetic_congestion(profile, dt, rain_mm=0.0, holiday=False, rng=random):
    """Congestion entre 0 et 1 pour un profil de route à un instant donné (dt en heure locale)."""
    h = dt.hour + dt.minute / 60
    w = WEIGHTS[profile]
    am = w['am'] * _peak(h, 8.0, 1.0)
    mid = w['mid'] * _peak(h, 13.0, 1.2)
    pm = w['pm'] * _peak(h, 17.5, 1.3)
    rush = am + mid + pm

    day = dt.weekday()  # 0 = lundi
    if holiday or day == 6:
        factor = 0.45
    elif day == 5:
        factor = 0.60
    elif day == 4:
        factor = 0.90
    else:
        factor = 1.0

    rain_effect = 0.18 * min(rain_mm / 2, 1) * (0.3 + rush)
    value = 0.06 + rush * factor + rain_effect + rng.gauss(0, 0.04)
    return round(max(0.0, min(0.98, value)), 4)


def speeds(profile, congestion):
    """Vitesses cohérentes avec congestion = 1 - vitesse_actuelle / vitesse_fluide."""
    free = FREE_FLOW[profile]
    return round(free * (1 - congestion), 1), free