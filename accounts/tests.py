"""
Tests unitaires pour l'application Accounts (Authentification, Profil, HTMX, DRF).
"""
from django.test import TestCase, Client
from django.urls import reverse
from .models import CustomUser


class AccountsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = CustomUser.objects.create_user(
            username="testuser",
            email="testuser@greenmove.tn",
            password="securepassword123",
            first_name="Amine",
            last_name="Test",
            role=CustomUser.RoleChoices.DRIVER,
            vehicle_type=CustomUser.VehicleChoices.ELECTRIC,
            eco_points=450,
            home_address="Ariana Centre",
            work_address="Les Berges du Lac 2"
        )

    def test_login_view(self):
        """Vérifie la connexion d'un utilisateur valide."""
        response = self.client.post(reverse('accounts:login'), {
            'username': 'testuser',
            'password': 'securepassword123',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['user'].is_authenticated)

    def test_profile_requires_login(self):
        """Vérifie que la page de profil redirige les utilisateurs non connectés."""
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)

    def test_profile_access_logged_in(self):
        """Vérifie l'accès au profil d'un utilisateur connecté."""
        self.client.login(username='testuser', password='securepassword123')
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amine Test")
        self.assertContains(response, "450")

    def test_htmx_profile_edit(self):
        """Vérifie la mise à jour dynamique du profil via HTMX."""
        self.client.login(username='testuser', password='securepassword123')
        response = self.client.post(reverse('accounts:profile_edit_htmx'), {
            'first_name': 'Amine Modifié',
            'last_name': 'Test',
            'email': 'testuser@greenmove.tn',
            'role': CustomUser.RoleChoices.DRIVER,
            'vehicle_type': CustomUser.VehicleChoices.ELECTRIC,
            'home_address': 'La Marsa',
            'work_address': 'Lac 2',
        }, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Amine Modifié')
        self.assertEqual(self.user.home_address, 'La Marsa')

    def test_api_token_obtain(self):
        """Vérifie l'obtention d'un jeton JWT valide via l'API REST."""
        response = self.client.post(reverse('accounts:token_obtain_pair'), {
            'username': 'testuser',
            'password': 'securepassword123',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.json())
        self.assertIn('refresh', response.json())
