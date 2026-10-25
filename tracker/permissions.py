from rest_framework.permissions import BasePermission


class IsTripOwner(BasePermission):
    """Only the trip owner may retrieve or mutate a trip API resource."""

    def has_object_permission(self, request, view, obj):
        return request.user.is_authenticated and obj.user_id == request.user.pk
