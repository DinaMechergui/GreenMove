"""Rapport hebdomadaire : HTML -> PDF (WeasyPrint) envoyé par e-mail.

Si WeasyPrint ou ses bibliothèques système (Pango/GTK) sont absents, le rapport est
envoyé en pièce jointe HTML plutôt que de faire échouer la tâche.
"""
import logging

from django.core.mail import EmailMessage
from django.template.loader import render_to_string
from django.utils import timezone

from . import planning
from .explain import explain_plan

logger = logging.getLogger(__name__)


def build_report_context(user):
    plan = planning.optimize_week(user)
    return {
        'user': user, 'today': timezone.localdate(), 'plan': plan,
        'profile': planning.weekly_profile(user, weeks=1),
        'history': planning.weekly_history(user, weeks=4),
        'budget': planning.carbon_budget_status(user),
        'impact': planning.simulate_impact(user, 1, plan),
        'typology': planning.classify_user(user),
        'explanations': explain_plan(plan),
    }


def render_report(user):
    """Retourne (bytes, mimetype, extension)."""
    html = render_to_string('planner/report.html', build_report_context(user))
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf(), 'application/pdf', 'pdf'
    except Exception as exc:  # ImportError / OSError (libs GTK manquantes)
        logger.warning("PDF indisponible (%s) : envoi du rapport en HTML", exc)
        return html.encode('utf-8'), 'text/html', 'html'


def send_weekly_report(user):
    if not user.email or not user.is_active:
        return False
    content, mimetype, ext = render_report(user)
    msg = EmailMessage(
        subject='GreenMove : votre rapport hebdomadaire',
        body=f"Bonjour {user.first_name or user.username},\n\nVotre rapport éco-mobilité de la semaine est en pièce jointe.",
        to=[user.email],
    )
    msg.attach(f'greenmove_rapport_{timezone.localdate()}.{ext}', content, mimetype)
    msg.send(fail_silently=True)
    return True
