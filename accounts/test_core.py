"""Tests : audit, rôles, RGPD."""
from django.test import TestCase
from django.urls import reverse

from .models import AuditLog, CustomUser


class AccountsCoreTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('sana', 'sana@greenmove.tn', 'pass12345!', first_name='Sana')

    def test_new_user_is_citizen(self):
        self.assertTrue(self.user.groups.filter(name='Citoyen').exists())

    def test_login_and_failure_are_audited(self):
        self.client.post(reverse('accounts:login'), {'username': 'sana', 'password': 'pass12345!'})
        self.assertTrue(AuditLog.objects.filter(action='LOGIN', user=self.user).exists())
        self.client.logout()
        self.client.post(reverse('accounts:login'), {'username': 'sana', 'password': 'bad'})
        self.assertTrue(AuditLog.objects.filter(action='LOGIN_FAILED', username='sana').exists())

    def test_profile_update_audited_but_not_points(self):
        self.user.eco_points += 5
        self.user.save(update_fields=['eco_points'])
        self.assertFalse(AuditLog.objects.filter(action='PROFILE_UPDATE').exists())
        self.user.bio = 'x'
        self.user.save()
        self.assertTrue(AuditLog.objects.filter(action='PROFILE_UPDATE').exists())

    def test_export_json_and_zip(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('accounts:export_data'))
        self.assertEqual(r['Content-Type'], 'application/json')
        self.assertNotIn(b'pbkdf2', r.content)
        z = self.client.get(reverse('accounts:export_data') + '?format=zip')
        self.assertEqual(z['Content-Type'], 'application/zip')

    def test_delete_account_anonymises(self):
        self.client.force_login(self.user)
        self.client.post(reverse('accounts:delete_account'), {'password': 'wrong'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.client.post(reverse('accounts:delete_account'), {'password': 'pass12345!'})
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.username.startswith('anonyme_'))
        self.assertEqual(self.user.first_name, '')

    def test_audit_api_admin_only(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('accounts:api_audit')).status_code, 403)
        admin = CustomUser.objects.create_superuser('boss', 'boss@greenmove.tn', 'pass12345!')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('accounts:api_audit')).status_code, 200)
