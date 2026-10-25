"""Conformité RGPD : export des données (JSON/ZIP) et suppression avec anonymisation."""
import io
import json
import zipfile
import uuid

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.utils import timezone

from .models import AuditLog

_PROFILE_EXCLUDE = {'password'}


def _model_to_dict(obj):
    data = {}
    for field in obj._meta.concrete_fields:
        if field.name in _PROFILE_EXCLUDE:
            continue
        value = field.value_from_object(obj)
        if isinstance(field, (models.FileField,)):
            value = str(value) if value else None
        data[field.name] = value
    return data


def collect_user_data(user):
    """Rassemble toutes les données liées à l'utilisateur (relations inverses incluses)."""
    export = {
        'exported_at': timezone.now(),
        'profile': _model_to_dict(user),
        'audit_log': [_model_to_dict(a) for a in user.audit_logs.all()],
        'related': {},
    }
    for rel in user._meta.related_objects:
        if not rel.auto_created or rel.related_model is AuditLog:
            continue
        if not (rel.one_to_many or rel.one_to_one):
            continue
        model = rel.related_model
        if model._meta.app_label in ('admin', 'auth', 'sessions', 'contenttypes'):
            continue
        try:
            qs = model._default_manager.filter(**{rel.field.name: user})
            export['related'][f'{model._meta.app_label}.{model._meta.model_name}'] = [
                _model_to_dict(o) for o in qs
            ]
        except Exception:  # un module tiers ne doit pas casser l'export
            continue
    return export


def export_json_bytes(user):
    return json.dumps(collect_user_data(user), cls=DjangoJSONEncoder, indent=2, ensure_ascii=False).encode('utf-8')


def export_zip_bytes(user):
    data = collect_user_data(user)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('profile.json', json.dumps(data['profile'], cls=DjangoJSONEncoder, indent=2, ensure_ascii=False))
        zf.writestr('audit_log.json', json.dumps(data['audit_log'], cls=DjangoJSONEncoder, indent=2, ensure_ascii=False))
        for name, rows in data['related'].items():
            zf.writestr(f'{name}.json', json.dumps(rows, cls=DjangoJSONEncoder, indent=2, ensure_ascii=False))
    return buf.getvalue()


@transaction.atomic
def delete_account(user):
    """Anonymise le compte (les trajets restent pour les statistiques, sans lien d'identité)."""
    token = uuid.uuid4().hex[:12]
    # Les traces GPS sont identifiantes : on les efface, les statistiques de trajets restent.
    for rel in user._meta.related_objects:
        model = rel.related_model
        if rel.auto_created and (rel.one_to_many or rel.one_to_one) and any(
                f.name == 'gps_points' for f in model._meta.get_fields()):
            model._default_manager.filter(**{rel.field.name: user}).update(gps_points=[])
    AuditLog.objects.filter(user=user).update(username='anonyme', ip_address=None, detail='')
    user.username = f'anonyme_{token}'
    user.email = f'{token}@anonymized.invalid'
    user.first_name = user.last_name = ''
    user.phone_number = ''
    user.bio = ''
    user.home_address = user.work_address = ''
    user.home_lat = user.home_lon = user.work_lat = user.work_lon = None
    user.avatar = None
    user.vehicle_model = ''
    user.is_active = False
    user.set_unusable_password()
    user.save()
    user.groups.clear()
    return token
