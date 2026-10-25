"""
Vues pour l'application Core (pages publiques et vitrine GreenMove).
"""
from django.shortcuts import render
from django.http import JsonResponse
from .services.weather import get_tunis_weather

# Points d'intérêt et hubs de mobilité dans le Grand Tunis
TUNIS_HUBS = [
    {
        "name": "Hub Technologique Lac 2",
        "category": "Covoiturage & Bornes Électriques",
        "lat": 36.8392,
        "lon": 10.2447,
        "icon": "lightning-charge-fill",
        "description": "Zone d'affaires majeure, 12 bornes de recharge rapide et station de covoiturage GreenMove.",
        "co2_saved_today": "480 kg",
    },
    {
        "name": "Pôle Intermodal Ariana Centre",
        "category": "Interconnexion Métro & Vélos",
        "lat": 36.8625,
        "lon": 10.1956,
        "icon": "bicycle",
        "description": "Correspondance Ligne 2 du Métro, parking relais et abri à vélos sécurisé.",
        "co2_saved_today": "310 kg",
    },
    {
        "name": "Station Verte La Marsa Plage",
        "category": "Mobilité Douce & TGM",
        "lat": 36.8782,
        "lon": 10.3247,
        "icon": "tree-fill",
        "description": "Terminus TGM, pistes cyclables côtières et point de rencontre pour covoiturage nord.",
        "co2_saved_today": "260 kg",
    },
    {
        "name": "Hub Campus Manouba",
        "category": "Covoiturage Étudiant & Métro 4",
        "lat": 36.8118,
        "lon": 10.0632,
        "icon": "people-fill",
        "description": "Foyer universitaire, fort taux de trajets partagés vers Centre-ville et Ariana.",
        "co2_saved_today": "520 kg",
    },
    {
        "name": "Éco-Gare Tunis Centre (Barcelone)",
        "category": "Nœud Central Multimodal",
        "lat": 36.7950,
        "lon": 10.1800,
        "icon": "signpost-split-fill",
        "description": "Convergence de toutes les lignes de métro, trains de banlieue et bus SNCFT/TRANSTU.",
        "co2_saved_today": "890 kg",
    },
    {
        "name": "Station Le Bardo - Patrimoine & Vert",
        "category": "Covoiturage & Ligne 4",
        "lat": 36.8090,
        "lon": 10.1415,
        "icon": "shield-check",
        "description": "Liaison ouest de Tunis, station d'autopartage et de dépose-minute bas-carbone.",
        "co2_saved_today": "210 kg",
    },
    {
        "name": "Hub Carthage Présidence / Amilcar",
        "category": "TGM & Navettes Partagées",
        "lat": 36.8530,
        "lon": 10.3315,
        "icon": "geo-alt-fill",
        "description": "Dessert les facultés et zones résidentielles de la banlieue nord.",
        "co2_saved_today": "175 kg",
    },
    {
        "name": "Pôle Sud Ben Arous / Mégrine",
        "category": "Covoiturage Industriel & Ligne 1",
        "lat": 36.7531,
        "lon": 10.2189,
        "icon": "buildings-fill",
        "description": "Départ des trajets domicile-travail vers les zones industrielles de Ben Arous.",
        "co2_saved_today": "430 kg",
    },
]


def home(request):
    """
    Page d'accueil principale de GreenMove.
    Fournit les statistiques d'impact, les données météo et les hubs de Tunis.
    """
    weather = get_tunis_weather()

    # Statistiques globales de démonstration (pour CountUp.js)
    impact_stats = {
        'co2_saved_tons': 142.8,       # Tonnes de CO2 évitées
        'shared_rides_count': 3840,    # Trajets partagés réalisés
        'green_km_traveled': 89250,    # Kilomètres verts parcourus
        'trees_planted_equiv': 7140,   # Arbres équivalents
        'active_members': 1250,        # Éco-navetteurs actifs
    }

    context = {
        'weather': weather,
        'impact_stats': impact_stats,
        'hubs': TUNIS_HUBS,
    }
    return render(request, 'core/home.html', context)


def weather_snippet(request):
    """
    Vue fragment HTMX pour rafraîchir le widget météo sans recharger la page.
    """
    weather = get_tunis_weather()
    return render(request, 'core/includes/weather_widget.html', {'weather': weather})


def about(request):
    """
    Page À Propos présentant la mission et l'architecture de GreenMove.
    """
    return render(request, 'core/about.html')


def handler404(request, exception=None):
    """Page d'erreur 404 personnalisée."""
    return render(request, '404.html', status=404)


def handler500(request):
    """Page d'erreur 500 personnalisée."""
    return render(request, '500.html', status=500)
