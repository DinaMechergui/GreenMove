"""Signaux : journal d'audit et rôles Citoyen / Admin (Groups)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.signals import user_logged_in, user_logged_out, user_login_failed
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .audit import log_event
from .models import AuditLog, Profile

CITIZEN_GROUP = 'Citoyen'
ADMIN_GROUP = 'Admin'

# Mises à jour techniques qui ne sont pas des modifications de profil.
_TECHNICAL_FIELDS = {'last_login', 'eco_points'}


@receiver(user_logged_in)
def on_login(sender, request, user, **kwargs):
    log_event(AuditLog.Action.LOGIN, user, request=request)


@receiver(user_logged_out)
def on_logout(sender, request, user, **kwargs):
    if user is not None:
        log_event(AuditLog.Action.LOGOUT, user, request=request)


@receiver(user_login_failed)
def on_login_failed(sender, credentials, request=None, **kwargs):
    log_event(AuditLog.Action.LOGIN_FAILED, request=request,
              username=str(credentials.get('username', ''))[:150])


@receiver(post_save, sender=get_user_model())
def on_user_saved(sender, instance, created, update_fields=None, **kwargs):
    if created:
        group, _ = Group.objects.get_or_create(name=CITIZEN_GROUP)
        instance.groups.add(group)
        Profile.objects.get_or_create(user=instance)
        return
    if update_fields and set(update_fields) <= _TECHNICAL_FIELDS:
        return
    log_event(AuditLog.Action.PROFILE_UPDATE, instance,
              detail=', '.join(sorted(update_fields)) if update_fields else '')


@receiver(post_migrate)
def create_roles(sender, **kwargs):
    """Crée les groupes Citoyen/Admin (idempotent) après les migrations d'accounts."""
    if getattr(sender, 'name', None) != 'accounts':
        return
    Group.objects.get_or_create(name=CITIZEN_GROUP)
    admin_group, _ = Group.objects.get_or_create(name=ADMIN_GROUP)
    admin_group.permissions.set(Permission.objects.filter(
        content_type__app_label='accounts', content_type__model__in=['customuser', 'auditlog'],
    ))
