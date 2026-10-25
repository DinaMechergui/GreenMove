"""Tests : préférences de mobilité (Profile), API DRF Préférences, export RGPD."""
from django.test import TestCase
from django.urls import reverse
from .models import CustomUser, Profile


class ProfilePrefsTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('prefs_user', 'prefs@greenmove.tn', 'pass12345!')
        self.client.force_login(self.user)

    def test_preferences_page_loads(self):
        resp = self.client.get(reverse('accounts:preferences'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'form')

    def test_preferences_update(self):
        resp = self.client.post(reverse('accounts:preferences'), {
            'city': 'Ariana',
            'preferred_mode': 'METRO',
            'carbon_goal_kg': 50,
            'language': 'fr',
        })
        self.assertIn(resp.status_code, (200, 302))
        profile = Profile.objects.get(user=self.user)
        self.assertEqual(profile.city, 'Ariana')
        self.assertEqual(profile.preferred_mode, 'METRO')

    def test_api_preferences_get(self):
        resp = self.client.get(reverse('accounts:api_preferences'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('preferred_mode', resp.json())

    def test_api_preferences_update(self):
        resp = self.client.patch(reverse('accounts:api_preferences'),
                                 data={'carbon_goal_kg': 40, 'preferred_mode': 'BUS',
                                       'city': 'Tunis', 'language': 'fr'},
                                 content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['carbon_goal_kg'], 40.0)

    def test_api_preferences_validates_negative_goal(self):
        resp = self.client.patch(reverse('accounts:api_preferences'),
                                 data={'carbon_goal_kg': -5, 'preferred_mode': 'BUS',
                                       'city': 'Tunis', 'language': 'fr'},
                                 content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    def test_profile_autocreated_on_request(self):
        """Le profil est créé automatiquement s'il n'existe pas."""
        Profile.objects.filter(user=self.user).delete()
        resp = self.client.get(reverse('accounts:api_preferences'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(Profile.objects.filter(user=self.user).exists())
