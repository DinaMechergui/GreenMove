"""
Tests unitaires et d'intégration pour le module EcoRewards & Gamification.
Vérifie :
1. Calculs scientifiques des économies de CO2 et bonus (heures de pointe, météo).
2. Attribution des EcoPoints, journal des transactions et déblocage des badges.
3. Profilage comportemental IA (KMeans) et génération des défis progressifs.
4. Boutique de récompenses, génération et validation des QR codes coupons.
5. Vues, endpoints HTMX et intégrité des routes.
"""
from datetime import datetime, time, timedelta
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from match.models import Ride, RideBooking
from rewards.models import (
    Badge,
    UserBadge,
    EcoTransaction,
    PersonalizedChallenge,
    CollectiveChallenge,
    RewardPartner,
    RewardItem,
    UserCoupon,
    UserGamificationProfile,
)
from rewards.services.co2_calculator import (
    compute_ride_carbon_savings,
    award_ride_eco_points,
    is_peak_hour,
    get_or_create_gamification_profile,
)
from rewards.services.kmeans_profiler import (
    extract_user_behavioral_features,
    profile_user_with_kmeans,
    generate_personalized_challenges,
)
from rewards.services.qr_service import (
    generate_unique_coupon_code,
    generate_coupon_qr_base64,
)


class CarbonSavingsCalculationTests(TestCase):
    """Tests du modèle physique de calcul des émissions évitées."""

    def test_thermal_carpool_savings(self):
        """Un trajet thermique de 15 km avec 3 passagers (4 personnes) doit économiser du CO2."""
        data = compute_ride_carbon_savings(
            distance_km=15.0,
            vehicle_type='THERMAL_ECO',
            occupants_count=4,
            departure_dt=datetime(2026, 10, 15, 12, 0),  # Hors heure de pointe
        )
        self.assertGreater(data['total_co2_saved_kg'], 0)
        self.assertGreater(data['total_points'], 0)
        self.assertEqual(data['peak_bonus_pts'], 0)

    def test_peak_hour_bonus(self):
        """Un trajet pendant l'heure de pointe (8h15) doit octroyer +25% de bonus."""
        dt_peak = timezone.now().replace(hour=8, minute=15)
        self.assertTrue(is_peak_hour(dt_peak))

        data = compute_ride_carbon_savings(
            distance_km=10.0,
            vehicle_type='HYBRID',
            occupants_count=2,
            departure_dt=dt_peak,
        )
        self.assertGreater(data['peak_bonus_pts'], 0)
        self.assertEqual(data['total_points'], data['base_points'] + data['peak_bonus_pts'])

    def test_bad_weather_bonus(self):
        """Covoiturer par temps de pluie octroie un bonus météo solidaire (+15%)."""
        data = compute_ride_carbon_savings(
            distance_km=10.0,
            vehicle_type='ELECTRIC',
            occupants_count=2,
            weather_condition="Pluie modérée",
        )
        self.assertGreater(data['weather_bonus_pts'], 0)


class EcoRewardsInterconnectionTests(TestCase):
    """Tests de l'interconnexion Match ➔ Rewards (Trajet Roua -> Points Skander)."""

    def setUp(self):
        self.driver = CustomUser.objects.create_user(
            username='roua_conductrice',
            email='roua@greenmove.tn',
            password='Password123!',
            eco_points=100,
            vehicle_type=CustomUser.VehicleChoices.HYBRID,
        )
        self.passenger = CustomUser.objects.create_user(
            username='skander_passager',
            email='skander@greenmove.tn',
            password='Password123!',
            eco_points=50,
        )

        self.ride = Ride.objects.create(
            user=self.driver,
            ride_type=Ride.RideTypeChoices.OFFER,
            origin_address="La Marsa Corniche",
            origin_lat=36.8782,
            origin_lon=10.3247,
            destination_address="Les Berges du Lac 2",
            destination_lat=36.8392,
            destination_lon=10.2447,
            departure_datetime=timezone.now() + timedelta(hours=2),
            seats_available=3,
        )

        self.booking = RideBooking.objects.create(
            ride=self.ride,
            passenger=self.passenger,
            status=RideBooking.StatusChoices.ACCEPTED,
        )

        self.col_challenge = CollectiveChallenge.objects.create(
            title="Challenge Test Tunis",
            target_co2_kg=1000.0,
            current_co2_kg=100.0,
            end_date=timezone.now().date() + timedelta(days=10),
            is_active=True,
        )

        self.badge = Badge.objects.create(
            slug='premier-trajet-test',
            name='Premier Trajet Test',
            threshold_type=Badge.ThresholdTypeChoices.RIDES_COUNT,
            threshold_value=1.0,
            points_reward=50,
        )

    def test_award_ride_points_credits_driver_and_passenger(self):
        initial_driver_pts = self.driver.eco_points
        initial_passenger_pts = self.passenger.eco_points

        result = award_ride_eco_points(self.ride)

        self.driver.refresh_from_db()
        self.passenger.refresh_from_db()
        self.col_challenge.refresh_from_db()

        # Points augmentés
        self.assertGreater(self.driver.eco_points, initial_driver_pts)
        self.assertGreater(self.passenger.eco_points, initial_passenger_pts)

        # Transactions enregistrées
        driver_tx = EcoTransaction.objects.filter(user=self.driver, ride=self.ride).first()
        passenger_tx = EcoTransaction.objects.filter(user=self.passenger, ride=self.ride).first()
        self.assertIsNotNone(driver_tx)
        self.assertIsNotNone(passenger_tx)
        self.assertGreater(driver_tx.co2_saved_kg, 0)

        # Jauge collective incrémentée
        self.assertGreater(self.col_challenge.current_co2_kg, 100.0)

        # Badge débloqué
        self.assertTrue(UserBadge.objects.filter(user=self.driver, badge=self.badge).exists())

    def test_contribute_to_collective_challenge(self):
        """Vérifie qu'un membre peut contribuer directement du CO2 à un défi collectif."""
        self.client.force_login(self.driver)
        initial_co2 = self.col_challenge.current_co2_kg
        initial_points = self.driver.eco_points

        response = self.client.post(reverse('rewards:contribute_collective', kwargs={'challenge_id': self.col_challenge.id}))
        self.assertEqual(response.status_code, 302)

        self.col_challenge.refresh_from_db()
        self.driver.refresh_from_db()

        self.assertEqual(self.col_challenge.current_co2_kg, initial_co2 + 5.0)
        self.assertEqual(self.driver.eco_points, initial_points + 50)
        self.assertTrue(self.col_challenge.participants.filter(id=self.driver.id).exists())


class KMeansPersonalizedChallengesTests(TestCase):
    """Tests du profilage comportemental et de la difficulté progressive des défis."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='yathreb_commuter',
            email='yathreb@greenmove.tn',
            password='Password123!',
            eco_points=200,
        )

    def test_kmeans_clustering_and_adaptive_challenges(self):
        cluster_id = profile_user_with_kmeans(self.user)
        self.assertIn(cluster_id, [0, 1, 2, 3])

        challenges = generate_personalized_challenges(self.user, force_refresh=True)
        self.assertEqual(len(challenges), 3)

        difficulties = [ch.difficulty for ch in challenges]
        self.assertIn('EASY', difficulties)
        self.assertIn('MEDIUM', difficulties)
        self.assertIn('HARD', difficulties)


class CouponQRCodeAndValidationTests(TestCase):
    """Tests de génération des coupons QR Code et du portail commerçant."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='amine_client',
            email='amine@greenmove.tn',
            password='Password123!',
            eco_points=500,
        )
        self.partner = RewardPartner.objects.create(
            name="Cosmitto Coffee Lac 2 Test",
            slug="cosmitto-test",
            validation_pin="2026",
        )
        self.reward = RewardItem.objects.create(
            partner=self.partner,
            title="Café Gratuit Test",
            points_cost=150,
            stock=10,
        )

    def test_qr_code_generation_format(self):
        code = generate_unique_coupon_code()
        self.assertTrue(code.startswith("GM-ECO-"))

        qr_b64 = generate_coupon_qr_base64(code, self.reward.title, self.user.username)
        self.assertTrue(qr_b64.startswith("data:image/png;base64,"))

    def test_redeem_and_merchant_validation_lifecycle(self):
        client = Client()
        client.force_login(self.user)

        # 1. Échanger des points contre un coupon
        resp = client.post(reverse('rewards:redeem', args=[self.reward.id]))
        self.assertEqual(resp.status_code, 302)

        self.user.refresh_from_db()
        self.assertEqual(self.user.eco_points, 350)  # 500 - 150

        coupon = UserCoupon.objects.filter(user=self.user, reward=self.reward).first()
        self.assertIsNotNone(coupon)
        self.assertEqual(coupon.status, 'VALID')

        # 2. Validation par le commerçant
        resp_val = client.post(reverse('rewards:verify_coupon'), {
            'coupon_code': coupon.coupon_code,
            'partner_pin': '2026',
        })
        self.assertEqual(resp_val.status_code, 200)

        coupon.refresh_from_db()
        self.assertEqual(coupon.status, 'USED')
        self.assertIsNotNone(coupon.used_at)

        # 3. Tentative de réutilisation (doit échouer)
        resp_reuse = client.post(reverse('rewards:verify_coupon'), {
            'coupon_code': coupon.coupon_code,
        })
        self.assertContains(resp_reuse, "déjà été validé")


class RewardsViewsAccessibilityTests(TestCase):
    """Tests d'accessibilité des vues principales du module."""

    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username='tester',
            email='tester@greenmove.tn',
            password='Password123!',
            eco_points=300,
        )
        self.client = Client()

    def test_public_pages_accessible(self):
        resp = self.client.get(reverse('rewards:index'))
        self.assertEqual(resp.status_code, 200)

        resp_lead = self.client.get(reverse('rewards:leaderboard'))
        self.assertEqual(resp_lead.status_code, 200)

        resp_cat = self.client.get(reverse('rewards:catalog'))
        self.assertEqual(resp_cat.status_code, 200)

        # La page d'évaluation scientifique IA est accessible
        resp_ai = self.client.get(reverse('rewards:ai_evaluation'))
        self.assertEqual(resp_ai.status_code, 200)
        self.assertContains(resp_ai, "Silhouette Score")

    def test_admin_dashboard_access_control(self):
        """Le dashboard admin doit interdire l'accès direct par URL aux non-staff."""
        # Non connecté -> redirection 302
        resp_anon = self.client.get(reverse('rewards:admin_dashboard'))
        self.assertEqual(resp_anon.status_code, 302)

        # Connecté non-staff -> redirection 302
        self.client.force_login(self.user)
        resp_user = self.client.get(reverse('rewards:admin_dashboard'))
        self.assertEqual(resp_user.status_code, 302)

        # Staff connecté -> accès accordé 200
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        resp_staff = self.client.get(reverse('rewards:admin_dashboard'))
        self.assertEqual(resp_staff.status_code, 200)

    def test_authenticated_dashboard_accessible(self):
        self.client.force_login(self.user)
        resp = self.client.get(reverse('rewards:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "EcoRewards")

    def test_coupon_crud_deletion(self):
        """Vérifie l'opération CRUD Delete sur les coupons."""
        self.client.force_login(self.user)
        partner = RewardPartner.objects.create(name="Bio Shop Lac", slug="bio-shop-lac")
        reward = RewardItem.objects.create(partner=partner, title="Tisane Bio", points_cost=50)
        coupon = UserCoupon.objects.create(
            user=self.user,
            reward=reward,
            coupon_code="GM-ECO-TEST99",
            status='USED'
        )
        self.assertEqual(UserCoupon.objects.filter(id=coupon.id).count(), 1)

        # Suppression
        resp = self.client.post(reverse('rewards:delete_coupon', args=[coupon.id]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(UserCoupon.objects.filter(id=coupon.id).count(), 0)
