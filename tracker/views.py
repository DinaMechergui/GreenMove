from django.shortcuts import render

def coming_soon(request):
    """Vue 'Bientôt disponible' pour le module Eco-Tracker."""
    return render(request, 'placeholder.html', {
        'module_title': 'Eco-Tracker (Bilan Carbone)',
        'module_icon': 'bi-speedometer2',
        'module_description': 'Suivez votre empreinte carbone personnelle et en entreprise, analysez l\'impact écologique de vos déplacements quotidiens et comparez vos performances.',
        'developer_name': 'Équipe Data & Climat',
        'eta': 'Hackathon Étape Suivante',
    })
