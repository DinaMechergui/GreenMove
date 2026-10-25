"""Permissions DRF réutilisables par tous les modules GreenMove."""
from rest_framework import permissions

from .signals import ADMIN_GROUP, CITIZEN_GROUP


def has_role(user, role):
    return bool(user and user.is_authenticated and user.groups.filter(name=role).exists())


class IsAdminRole(permissions.BasePermission):
    """Réservé aux membres du groupe Admin (ou superusers)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (user.is_superuser or has_role(user, ADMIN_GROUP)))


class IsCitizen(permissions.BasePermission):
    """Utilisateur authentifié du groupe Citoyen (ou Admin)."""

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and (
            user.is_superuser or has_role(user, CITIZEN_GROUP) or has_role(user, ADMIN_GROUP)))


class IsOwnerOrAdmin(permissions.BasePermission):
    """Objet accessible à son propriétaire (attribut `user`) ou à un admin."""

    def has_object_permission(self, request, view, obj):
        owner = getattr(obj, 'user', obj)
        user = request.user
        return owner == user or user.is_superuser or has_role(user, ADMIN_GROUP)
