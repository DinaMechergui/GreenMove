"""
Tests unitaires pour l'application MobilityMatch AI.
Couvre le moteur IA, le géocodage, le calcul d'itinéraires, les vues Web HTMX et l'API DRF.
"""
from django.test import TestCase, Client, SimpleTestCase
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
import json
from accounts.models import CustomUser
from .models import Ride, RideBooking
from .services.geocoding import geocode_address
from .services.routing import get_route_details, calculate_haversine_distance
from .services.ai_matcher import compute_ride_match_score, find_best_matches


class MobilityMatchAITests(TestCase):
    def setUp(self):
        self.client = Client()

        # Conducteur avec véhicule 100% électrique
        self.driver = CustomUser.objects.create_user(
            username="driver_green",
            email="driver@greenmove.tn",
            password="password123",
            first_name="Yassine",
            last_name="Conducteur",
            role=CustomUser.RoleChoices.DRIVER,
            vehicle_type=CustomUser.VehicleChoices.ELECTRIC,
            vehicle_model="Tesla Model 3",
            available_seats=3,
            eco_points=700,
            home_address="La Marsa",
            work_address="Les Berges du Lac 2"
        )

        # Passager
        self.passenger = CustomUser.objects.create_user(
            username="passenger_green",
            email="passenger@greenmove.tn",
            password="password123",
            first_name="Mariem",
            last_name="Passagère",
            role=CustomUser.RoleChoices.PASSENGER,
            eco_points=200,
            home_address="Ariana",
            work_address="Centre-ville"
        )

        # Trajet test
        self.ride = Ride.objects.create(
            user=self.driver,
            ride_type=Ride.RideTypeChoices.OFFER,
            origin_address="La Marsa Plage",
            origin_lat=36.8782,
            origin_lon=10.3247,
            destination_address="Les Berges du Lac 2",
            destination_lat=36.8392,
            destination_lon=10.2447,
            departure_datetime=timezone.now() + timedelta(hours=3),
            seats_available=3,
            price_tnd=2.5,
            is_recurring=True,
            description="Trajet régulier éco-friendly"
        )

    def test_geocoding_service(self):
        """Vérifie que le service de géocodage retourne des coordonnées valides pour Tunis."""
        coords = geocode_address("Ariana")
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords[0], 36.8625, places=2)
        self.assertAlmostEqual(coords[1], 10.1956, places=2)

    def test_routing_service(self):
        """Vérifie le calcul d'itinéraire et de l'empreinte carbone évitée."""
        details = get_route_details(36.8782, 10.3247, 36.8392, 10.2447)
        self.assertIn('distance_km', details)
        self.assertIn('duration_min', details)
        self.assertIn('coordinates', details)
        self.assertGreater(details['distance_km'], 0)
        self.assertGreater(details['co2_saved_kg'], 0)

    def test_ai_matching_engine(self):
        """Vérifie le calcul du score de correspondance IA multidimensionnel."""
        analysis = compute_ride_match_score(
            query_origin=(36.8780, 10.3240),
            query_dest=(36.8390, 10.2440),
            query_time=self.ride.departure_datetime,
            candidate_ride=self.ride
        )
        self.assertGreaterEqual(analysis['match_percentage'], 70)
        self.assertIn("Zéro Émission", analysis['vehicle_badge'])
        self.assertIn("Analyse IA", f"Analyse IA : {analysis['ai_verdict']}")

    def test_search_view(self):
        """Vérifie la page de recherche de trajets."""
        response = self.client.get(reverse('match:search'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La Marsa Plage")
        self.assertContains(response, "Les Berges du Lac 2")

    def test_search_view_htmx(self):
        """Vérifie la réponse partielle HTMX."""
        response = self.client.get(reverse('match:search'), HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Score IA")

    def test_ride_detail_view(self):
        """Vérifie la page de détails d'un trajet."""
        response = self.client.get(reverse('match:ride_detail', kwargs={'pk': self.ride.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Yassine")
        self.assertContains(response, "Tesla Model 3")

    def test_create_ride(self):
        """Vérifie la création d'un nouveau trajet et l'attribution de points écologiques."""
        self.client.login(username='driver_green', password='password123')
        initial_points = self.driver.eco_points

        response = self.client.post(reverse('match:create_ride'), {
            'ride_type': Ride.RideTypeChoices.OFFER,
            'origin_address': 'Le Bardo Centre',
            'destination_address': 'Centre-ville',
            'departure_date': timezone.now().date(),
            'departure_time_input': '08:30',
            'seats_available': 3,
            'price_tnd': 2.0,
            'description': 'Nouveau trajet test',
        })
        self.assertEqual(response.status_code, 302)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.eco_points, initial_points + 30)

    def test_book_ride(self):
        """Vérifie la réservation d'un trajet par un passager."""
        self.client.login(username='passenger_green', password='password123')
        initial_points = self.passenger.eco_points

        response = self.client.post(reverse('match:book_ride', kwargs={'pk': self.ride.id}), {
            'seats_requested': 1,
            'message': 'Bonjour ! Je réserve une place.',
        })
        self.assertEqual(response.status_code, 302)
        booking = RideBooking.objects.filter(ride=self.ride, passenger=self.passenger).first()
        self.assertIsNotNone(booking)
        self.passenger.refresh_from_db()
        self.assertEqual(self.passenger.eco_points, initial_points)
        self.assertEqual(booking.status, RideBooking.StatusChoices.PENDING)
        self.client.force_login(self.driver)
        self.client.post(reverse('match:manage_booking', kwargs={'booking_id': booking.pk}),
                         {'action': 'accept'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, RideBooking.StatusChoices.ACCEPTED)
        self.passenger.refresh_from_db()
        self.assertEqual(self.passenger.eco_points, initial_points + 20)
        self.ride.refresh_from_db()
        self.assertEqual(self.ride.seats_available, 2)

    def test_api_find_matches(self):
        """Vérifie l'endpoint REST d'IA pour le matching."""
        response = self.client.post(
            reverse('match:api_find_matches'),
            data={'origin': 'La Marsa', 'destination': 'Lac 2'},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('matches', data)
        self.assertGreater(len(data['matches']), 0)


# ==========================================
# 1. SIMILARITÉ DE TRAJECTOIRES (Fréchet/Hausdorff/chevauchement)
# ==========================================

from .services.similarity import trajectory_similarity, ride_similarity


class TrajectorySimilarityTests(TestCase):
    def test_identical_polyline(self):
        """Deux tracés identiques : Fréchet ≈ 0 et chevauchement = 100%."""
        line = [(36.8782, 10.3247), (36.8600, 10.3000), (36.8392, 10.2447)]
        result = trajectory_similarity(line, line)
        self.assertLess(result['frechet_m'], 1.0)
        self.assertGreaterEqual(result['overlap_pct'], 99.0)
        self.assertGreaterEqual(result['similarity_pct'], 99.0)
        self.assertIn(result['backend'], ('python', 'postgis'))

    def test_parallel_shifted_polyline(self):
        """Un tracé parallèle décalé réduit le chevauchement."""
        line_a = [(36.80, 10.18), (36.82, 10.20), (36.84, 10.22)]
        line_b = [(36.81, 10.18), (36.83, 10.20), (36.85, 10.22)]  # ~1.1 km au nord
        result = trajectory_similarity(line_a, line_b)
        self.assertGreater(result['hausdorff_m'], 500)
        self.assertLess(result['overlap_pct'], 60)
        self.assertLess(result['similarity_pct'], trajectory_similarity(line_a, line_a)['similarity_pct'])

    def test_ride_similarity_uses_polyline(self):
        """Le calcul entre deux Ride utilise leur polyline stockée."""
        driver = CustomUser.objects.create_user(
            username="sim_driver", email="sim@greenmove.tn", password="password123",
        )
        ride = Ride.objects.create(
            user=driver,
            origin_address="La Marsa", origin_lat=36.8782, origin_lon=10.3247,
            destination_address="Lac 2", destination_lat=36.8392, destination_lon=10.2447,
            departure_datetime=timezone.now() + timedelta(hours=3),
        )
        result = ride_similarity(ride, ride)
        self.assertGreaterEqual(result['overlap_pct'], 99.0)


# ==========================================
# 3. POINT DE RDV OPTIMAL (ISOCHRONES)
# ==========================================

from .services.isochrones import find_meeting_point, get_isochrone


class MeetingPointTests(TestCase):
    def test_isochrone_fallback_offline(self):
        """Sans clé ORS, l'isochrone tombe en repli géodésique (jamais d'erreur)."""
        iso = get_isochrone(36.8782, 10.3247, minutes=15)
        self.assertGreater(len(iso['coordinates']), 10)
        self.assertIn('source', iso)

    def test_meeting_point_nearby_users(self):
        """Deux utilisateurs proches → intersection des isochrones."""
        result = find_meeting_point((36.8782, 10.3247), (36.8700, 10.3100), minutes=15)
        self.assertIsNotNone(result['lat'])
        self.assertIsNotNone(result['lon'])
        self.assertEqual(result['method'], 'isochrone_intersection')
        self.assertGreater(len(result['geojson_a']), 10)
        self.assertGreater(len(result['geojson_b']), 10)

    def test_meeting_point_far_users_fallback(self):
        """Deux utilisateurs très éloignés → repli point médian sans erreur."""
        result = find_meeting_point((36.8782, 10.3247), (36.5000, 10.0000), minutes=5)
        self.assertIn(result['method'], ('isochrone_intersection', 'midpoint_fallback'))


# ==========================================
# 4. CLUSTERING DBSCAN DES TRAJECTOIRES RÉCURRENTS
# ==========================================

from .services.clusters import cluster_recurring_rides, join_group, suggest_mode
from .models import RideGroup


class DBSCANClusteringTests(TestCase):
    def setUp(self):
        self.driver = CustomUser.objects.create_user(
            username="cluster_driver", email="cluster@greenmove.tn",
            password="password123", role=CustomUser.RoleChoices.DRIVER,
        )
        when = timezone.now() + timedelta(days=1)
        # Groupe A : Marsa → Lac 2 (2 trajets quasi identiques)
        for i in range(2):
            Ride.objects.create(
                user=self.driver, ride_type=Ride.RideTypeChoices.OFFER,
                origin_address="La Marsa", origin_lat=36.8782 + i * 0.001, origin_lon=10.3247,
                destination_address="Lac 2", destination_lat=36.8392, destination_lon=10.2447,
                departure_datetime=when, is_recurring=True,
            )
        # Groupe B : Bardo → Manouba (loin du groupe A)
        for i in range(2):
            Ride.objects.create(
                user=self.driver, ride_type=Ride.RideTypeChoices.OFFER,
                origin_address="Le Bardo", origin_lat=36.8090 + i * 0.001, origin_lon=10.1415,
                destination_address="Manouba", destination_lat=36.8118, destination_lon=10.0632,
                departure_datetime=when, is_recurring=True,
            )
        # Trajet isolé (bruit DBSCAN) : Sidi Bou Saïd très loin
        Ride.objects.create(
            user=self.driver, ride_type=Ride.RideTypeChoices.OFFER,
            origin_address="Sidi Bou Saïd", origin_lat=36.8700, origin_lon=10.3420,
            destination_address="Ennasr", destination_lat=36.8710, destination_lon=10.1580,
            departure_datetime=when, is_recurring=True,
        )

    def test_dbscan_detects_two_clusters(self):
        clusters = cluster_recurring_rides(eps_m=1500, min_samples=2)
        self.assertEqual(len(clusters), 2)
        sizes = sorted(len(c['rides']) for c in clusters)
        self.assertEqual(sizes, [2, 2])
        for c in clusters:
            self.assertIn(c['mode'], ('COVOITURAGE', 'PEDIBUS', 'CONVOI_VELO'))
            self.assertTrue(c['label'])

    def test_join_group_persists(self):
        clusters = cluster_recurring_rides(eps_m=1500, min_samples=2)
        group = join_group([r.id for r in clusters[0]['rides']], self.driver)
        self.assertIsNotNone(group)
        self.assertEqual(group.members.filter(pk=self.driver.pk).count(), 1)
        self.assertEqual(group.rides.count(), len(clusters[0]['rides']))
        self.assertTrue(RideGroup.objects.filter(pk=group.pk).exists())

    def test_user_belongs_to_single_group(self):
        """Un utilisateur ne peut appartenir qu'à un seul groupe à la fois."""
        clusters = cluster_recurring_rides(eps_m=1500, min_samples=2)
        first = join_group([r.id for r in clusters[0]['rides']], self.driver)
        second = join_group([r.id for r in clusters[1]['rides']], self.driver)
        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(RideGroup.objects.filter(members=self.driver).count(), 1)
        self.assertFalse(first.members.filter(pk=self.driver.pk).exists())
        self.assertTrue(second.members.filter(pk=self.driver.pk).exists())

    def test_suggest_mode_pedibus_short_trip(self):
        """Trajets ≤ 4 km → suggestion Pédibus."""
        short = Ride.objects.filter(origin_address="La Marsa")
        rides = list(short)
        # Raccourcit le trajet pour simuler une distance piétonne (~1.5 km)
        for r in rides:
            r.destination_lat = r.origin_lat + 0.01
            r.destination_lon = r.origin_lon + 0.01
        self.assertEqual(suggest_mode(rides), 'PEDIBUS')


# ==========================================
# 7. CALCULATEUR DE PARTAGE DES FRAIS & CO2 PAR DUO
# ==========================================

from .services.costs import compute_duo_split, compute_custom_split, estimate_trip_cost


class CostSplitTests(TestCase):
    def setUp(self):
        self.driver = CustomUser.objects.create_user(
            username="cost_driver", email="cost@greenmove.tn",
            password="password123", role=CustomUser.RoleChoices.DRIVER,
        )
        self.ride = Ride.objects.create(
            user=self.driver,
            origin_address="Ariana", origin_lat=36.8625, origin_lon=10.1956,
            destination_address="Centre-ville", destination_lat=36.8000, destination_lon=10.1800,
            departure_datetime=timezone.now() + timedelta(hours=3),
            price_tnd=3.0,
        )

    def test_duo_split_math(self):
        result = compute_duo_split(self.ride, distance_km=10.0)
        self.assertEqual(result['trip_cost_tnd'], estimate_trip_cost(10.0))
        self.assertEqual(result['passenger_pays_tnd'], 3.0)
        self.assertEqual(result['driver_net_cost_tnd'], round(result['trip_cost_tnd'] - 3.0, 2))
        self.assertEqual(result['co2_duo_saved_kg'], 1.3)
        self.assertEqual(result['co2_per_person_kg'], 0.65)

    def test_duo_split_without_price_is_fifty_fifty(self):
        self.ride.price_tnd = 0
        self.ride.save(update_fields=['price_tnd'])
        result = compute_duo_split(self.ride, distance_km=10.0)
        self.assertEqual(result['passenger_pays_tnd'], round(result['trip_cost_tnd'] / 2, 2))

    def test_custom_split_group(self):
        result = compute_custom_split(distance_km=20, passengers=4, total_cost=40)
        self.assertEqual(result['per_person_tnd'], 10.0)
        self.assertEqual(result['co2_total_kg'], 2.6)


# ==========================================
# 6. AVIS → SCORE DE FIABILITÉ
# ==========================================

from .models import Review


class ReviewReliabilityTests(TestCase):
    def setUp(self):
        self.driver = CustomUser.objects.create_user(
            username="reviewed_driver", email="rev@greenmove.tn",
            password="password123", reliability_score=5.0,
        )
        self.p1 = CustomUser.objects.create_user(
            username="reviewer_1", email="r1@greenmove.tn", password="password123",
        )
        self.p2 = CustomUser.objects.create_user(
            username="reviewer_2", email="r2@greenmove.tn", password="password123",
        )
        self.ride = Ride.objects.create(
            user=self.driver,
            origin_address="La Marsa", origin_lat=36.8782, origin_lon=10.3247,
            destination_address="Lac 2", destination_lat=36.8392, destination_lon=10.2447,
            departure_datetime=timezone.now() + timedelta(hours=3),
        )

    def test_reviews_update_reliability_score(self):
        Review.objects.create(ride=self.ride, reviewer=self.p1,
                              reviewed_user=self.driver, rating=4, comment="Ponctuel")
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.reliability_score, 4.0)

        Review.objects.create(ride=self.ride, reviewer=self.p2,
                              reviewed_user=self.driver, rating=5)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.reliability_score, 4.5)

    def test_unique_review_per_ride_and_reviewer(self):
        Review.objects.create(ride=self.ride, reviewer=self.p1,
                              reviewed_user=self.driver, rating=3)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Review.objects.create(ride=self.ride, reviewer=self.p1,
                                  reviewed_user=self.driver, rating=5)


# ==========================================
# 2 & 3 & 5 & 6 : VUES DES NOUVELLES FONCTIONNALITÉS
# ==========================================


class FeatureViewsTests(TestCase):
    def setUp(self):
        self.driver = CustomUser.objects.create_user(
            username="feat_driver", email="feat@greenmove.tn",
            password="password123", role=CustomUser.RoleChoices.DRIVER,
        )
        self.passenger = CustomUser.objects.create_user(
            username="feat_passenger", email="feat2@greenmove.tn",
            password="password123", role=CustomUser.RoleChoices.PASSENGER,
        )
        self.ride = Ride.objects.create(
            user=self.driver,
            origin_address="La Marsa", origin_lat=36.8782, origin_lon=10.3247,
            destination_address="Lac 2", destination_lat=36.8392, destination_lon=10.2447,
            departure_datetime=timezone.now() + timedelta(hours=3),
            price_tnd=2.5,
        )

    # --- 3. Point de RDV ---
    def test_meeting_point_page(self):
        response = self.client.get(reverse('match:meeting_point'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Point de RDV")

    def test_api_meeting_point(self):
        response = self.client.post(
            reverse('match:api_meeting_point'),
            data={'alat': 36.8782, 'alon': 10.3247, 'blat': 36.8700, 'blon': 10.3100, 'minutes': 15},
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('lat', data)
        self.assertIn('lon', data)
        self.assertEqual(data['method'], 'isochrone_intersection')

    # --- 4. Groupes DBSCAN ---
    def test_groups_page(self):
        Ride.objects.filter(pk=self.ride.pk).update(is_recurring=True)
        response = self.client.get(reverse('match:groups'))
        self.assertEqual(response.status_code, 200)

    def test_join_group_requires_login(self):
        response = self.client.post(
            reverse('match:groups'), {'ride_ids': [self.ride.id]}, follow=False
        )
        self.assertEqual(response.status_code, 302)

    def test_join_group_authenticated(self):
        self.client.login(username='feat_driver', password='password123')
        response = self.client.post(
            reverse('match:groups'), {'ride_ids': [self.ride.id]}, follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            RideGroup.objects.filter(members=self.driver).count(), 1
        )

    # --- 5. Chat ---
    def test_chat_creates_room_and_suggestions_for_owner(self):
        self.client.login(username='feat_driver', password='password123')
        response = self.client.get(reverse('match:chat_room', kwargs={'pk': self.ride.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Messages d'accueil suggérés")
        from .models import ChatRoom
        room = ChatRoom.objects.get(ride=self.ride)
        self.assertEqual(room.messages.filter(is_suggestion=True).count(), 3)

    def test_chat_restricted_to_participants(self):
        RideBooking.objects.create(
            ride=self.ride, passenger=self.passenger,
            status=RideBooking.StatusChoices.ACCEPTED,
        )
        outsider = CustomUser.objects.create_user(
            username="outsider", email="out@greenmove.tn", password="password123"
        )
        self.client.login(username='outsider', password='password123')
        response = self.client.get(
            reverse('match:chat_room', kwargs={'pk': self.ride.id}), follow=True
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "chat-messages")

    def test_chat_http_post_and_get_fallback(self):
        from .models import ChatRoom
        room = ChatRoom.objects.create(ride=self.ride)
        self.client.login(username='feat_driver', password='password123')

        # Envoi via fallback HTTP POST
        post_url = reverse('match:chat_post_message', kwargs={'room_id': room.id})
        res = self.client.post(post_url, data=json.dumps({'content': 'Bonjour du conducteur !'}), content_type='application/json')
        self.assertEqual(res.status_code, 200)
        payload = res.json()
        self.assertEqual(payload['status'], 'ok')
        self.assertEqual(payload['message']['content'], 'Bonjour du conducteur !')

        # Lecture via fallback HTTP GET
        get_url = reverse('match:chat_get_messages', kwargs={'room_id': room.id})
        res_get = self.client.get(get_url)
        self.assertEqual(res_get.status_code, 200)
        get_payload = res_get.json()
        self.assertEqual(len(get_payload['messages']), 1)
        self.assertEqual(get_payload['messages'][0]['content'], 'Bonjour du conducteur !')

    # --- 6. Suivi live ---
    def test_create_tracking_link_and_live_page(self):
        self.client.login(username='feat_driver', password='password123')
        response = self.client.post(
            reverse('match:create_tracking_link', kwargs={'pk': self.ride.id})
        )
        self.assertEqual(response.status_code, 302)
        from .models import TrackingLink
        link = TrackingLink.objects.get(ride=self.ride, owner=self.driver)
        self.assertTrue(link.is_valid)

        page = self.client.get(reverse('match:live_tracking', kwargs={'token': link.token}))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Suivi live")

    def test_tracking_link_forbidden_for_others(self):
        self.client.login(username='feat_passenger', password='password123')
        response = self.client.post(
            reverse('match:create_tracking_link', kwargs={'pk': self.ride.id})
        )
        self.assertEqual(response.status_code, 302)
        from .models import TrackingLink
        self.assertFalse(TrackingLink.objects.filter(ride=self.ride).exists())

    # --- 6. SOS ---
    def test_trigger_sos_creates_alert(self):
        self.client.login(username='feat_passenger', password='password123')
        response = self.client.post(
            reverse('match:trigger_sos', kwargs={'pk': self.ride.id}),
            {'lat': '36.85', 'lon': '10.30', 'message': 'Aidez-moi'},
        )
        self.assertEqual(response.status_code, 302)
        from .models import SOSAlert
        alert = SOSAlert.objects.get(ride=self.ride, user=self.passenger)
        self.assertEqual(alert.status, 'ACTIVE')
        self.assertAlmostEqual(alert.latitude, 36.85)

    # --- 6. Avis ---
    def test_create_review_updates_reliability_and_points(self):
        RideBooking.objects.create(
            ride=self.ride, passenger=self.passenger,
            status=RideBooking.StatusChoices.ACCEPTED,
        )
        self.client.login(username='feat_passenger', password='password123')
        initial_points = self.passenger.eco_points

        response = self.client.post(
            reverse('match:create_review', kwargs={'pk': self.ride.id}),
            {'rating': 5, 'comment': 'Excellent trajet !'},
        )
        self.assertEqual(response.status_code, 302)
        review = Review.objects.get(ride=self.ride, reviewer=self.passenger)
        self.assertEqual(review.rating, 5)
        self.driver.refresh_from_db()
        self.assertEqual(self.driver.reliability_score, 5.0)
        self.passenger.refresh_from_db()
        self.assertEqual(self.passenger.eco_points, initial_points + 15)

    def test_cannot_review_own_ride(self):
        self.client.login(username='feat_driver', password='password123')
        self.client.post(
            reverse('match:create_review', kwargs={'pk': self.ride.id}),
            {'rating': 5},
        )
        self.assertFalse(Review.objects.filter(ride=self.ride).exists())

    # --- 7. Calculateur ---
    def test_split_calculator_page_and_htmx(self):
        response = self.client.get(reverse('match:split_calculator'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Calculateur")

        response = self.client.post(
            reverse('match:split_calculator'), {'distance_km': 10, 'passengers': 2}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "8,5")  # coût estimé de 10 km = 8,5 DT (format fr)

        htmx = self.client.post(
            reverse('match:split_calculator') + '?partial=1',
            {'ride': self.ride.id}, HTTP_HX_REQUEST='true'
        )
        self.assertEqual(htmx.status_code, 200)
        self.assertContains(htmx, "conducteur")

    def test_ride_detail_shows_new_actions(self):
        response = self.client.get(reverse('match:ride_detail', kwargs={'pk': self.ride.id}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Partage des frais & CO₂")
        self.assertContains(response, "Fiabilité")

    # --- 2. Score multi-critères ---
    def test_match_breakdown_contains_all_criteria(self):
        analysis = compute_ride_match_score(
            (36.8780, 10.3240), (36.8390, 10.2440),
            self.ride.departure_datetime, self.ride,
        )
        for key in ('overlap', 'spatial', 'temporal', 'detour', 'preferences', 'reliability', 'eco'):
            self.assertIn(key, analysis['breakdown'])
        self.assertIn('similarity', analysis)

    def test_women_only_preference_blocks_match(self):
        driver = self.driver
        driver.ride_preference = CustomUser.RidePreferenceChoices.WOMEN_ONLY
        driver.gender = CustomUser.GenderChoices.FEMALE
        driver.save(update_fields=['ride_preference', 'gender'])

        man = CustomUser.objects.create_user(
            username="male_rider", email="male@greenmove.tn", password="password123",
            gender=CustomUser.GenderChoices.MALE,
        )
        analysis = compute_ride_match_score(
            (36.8782, 10.3247), (36.8392, 10.2447),
            self.ride.departure_datetime, self.ride, query_user=man,
        )
        self.assertFalse(analysis['preference_ok'])
        self.assertEqual(analysis['breakdown']['preferences'], 0)

    def test_smoker_mismatch_penalized(self):
        nonsmoker = CustomUser.objects.create_user(
            username="nonsmoker", email="ns@greenmove.tn", password="password123",
            is_smoker=False,
        )
        self.driver.is_smoker = True
        self.driver.save(update_fields=['is_smoker'])

        analysis = compute_ride_match_score(
            (36.8782, 10.3247), (36.8392, 10.2447),
            self.ride.departure_datetime, self.ride, query_user=nonsmoker,
        )
        self.assertEqual(analysis['breakdown']['preferences'], 0)
        self.assertFalse(analysis['preference_ok'])
        self.assertIn("non-fumeur", analysis['preference_reason'])


# ==========================================
# 8. NOTIFICATIONS TELEGRAM (désactivé sans token)
# ==========================================

from .services import telegram as telegram_service


class TelegramTests(SimpleTestCase):
    def test_send_telegram_disabled_without_token(self):
        """Sans token, l'envoi est un no-op propre qui retourne False."""
        self.assertFalse(telegram_service.telegram_enabled())
        self.assertFalse(telegram_service.send_telegram("Test GreenMove"))

    def test_notify_wrappers_do_not_raise(self):
        class FakeUser:
            def get_full_name(self):
                return "Utilisateur Test"
            username = "test"
        class FakeAlert:
            user = FakeUser()
            ride = None
            latitude = None
            longitude = None
            created_at = timezone.now()
        self.assertFalse(telegram_service.notify_sos(FakeAlert()))
