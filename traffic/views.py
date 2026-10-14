from django.shortcuts import render

def coming_soon(request):
    """Vue 'Bientôt disponible' pour le module Traffic Eco-Prédictif."""
    return render(request, 'placeholder.html', {
        'module_title': 'Traffic Eco-Prédictif',
        'module_icon': 'bi-stoplights',
        'module_description': 'Anticipation des embouteillages du Grand Tunis, prédiction des zones de ralentissement et calcul d\'itinéraires alternatifs à faible émission de gaz à effet de serre.',
        'developer_name': 'Équipe IA & Données Urbaines',
        'eta': 'Hackathon Étape Suivante',
    })
