"""Helper d'audit réutilisable par tous les modules (ex. tracker pour les accès GPS)."""
from .models import AuditLog


def client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR') or None


def log_event(action, user=None, detail='', request=None, username=''):
    """Enregistre un évènement. Usage : log_event(AuditLog.Action.GPS_ACCESS, user, 'trip #3', request)."""
    if user is not None and not getattr(user, 'is_authenticated', True):
        user = None
    return AuditLog.objects.create(
        user=user,
        username=username or (user.get_username() if user else ''),
        action=action,
        detail=detail,
        ip_address=client_ip(request),
    )
