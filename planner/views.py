from django.shortcuts import render

def coming_soon(request):
    """Vue 'Bientôt disponible' pour le module Green Planner."""
    return render(request, 'placeholder.html', {
        'module_title': 'Green Planner (Planificateur Multimodal)',
        'module_icon': 'bi-signpost-split',
        'module_description': 'Combinez de façon intelligente le métro léger de Tunis, la ligne TGM, les bus, le vélo partagé et la marche pour des itinéraires 100% verts optimisés.',
        'developer_name': 'Équipe Transports Publics & Cartographie',
        'eta': 'Hackathon Étape Suivante',
    })
