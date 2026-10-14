from django.shortcuts import render

def coming_soon(request):
    """Vue 'Bientôt disponible' pour le module Eco-Rewards."""
    return render(request, 'placeholder.html', {
        'module_title': 'Eco-Rewards & Gamification',
        'module_icon': 'bi-trophy',
        'module_description': 'Gagnez des GreenPoints à chaque kilomètre bas-carbone, relevez des défis éco-citoyens entre collègues ou voisins et échangez vos points contre des avantages chez nos commerçants partenaires.',
        'developer_name': 'Équipe Gamification & Partenariats',
        'eta': 'Hackathon Étape Suivante',
    })
