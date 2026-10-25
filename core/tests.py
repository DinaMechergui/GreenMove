"""
Tests unitaires pour l'Étape 1 (Initialisation et architecture de base).
"""
from django.test import TestCase, Client
from django.urls import reverse
from accounts.models import CustomUser
from match.models import Ride, RideBooking


class CoreInitializationTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_homepage_status(self):
        """Vérifie que la page d'accueil répond avec le code HTTP 200."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)

    def test_context_processor_variables(self):
        """Vérifie que le processeur de contexte GreenMove injecte les variables attendues."""
        response = self.client.get(reverse('core:home'))
        self.assertIn('PLATFORM_NAME', response.context)
        self.assertEqual(response.context['PLATFORM_NAME'], 'GreenMove')
        self.assertIn('IS_RTL', response.context)

    def test_placeholder_views(self):
        """Vérifie que les modules vides 'Bientôt disponible' s'affichent correctement."""
        for app in ['tracker:index', 'traffic:index', 'rewards:index']:
            res = self.client.get(reverse(app))
            self.assertEqual(res.status_code, 200)
            self.assertContains(res, "Bientôt disponible")


class DemoDataTests(TestCase):
    def test_user_creation(self):
        """Vérifie la création d'un utilisateur et les propriétés éco."""
        user = CustomUser.objects.create_user(
            username="eco_tester",
            email="tester@greenmove.tn",
            password="testpassword",
            vehicle_type=CustomUser.VehicleChoices.ELECTRIC,
            eco_points=600
        )
        self.assertEqual(user.eco_badge, "Zéro Émission")
        self.assertGreater(user.co2_saved_kg, 0)
