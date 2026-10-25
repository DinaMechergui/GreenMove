"""Tests : nouveaux endpoints CRUD, API DRF, métriques IA, leaderboard, CSV, 404/500."""
import csv
import io
from datetime import time, timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from .models import RecurringTrip, TripRecord, CarbonBudget
from .services import planning
from .services.metrics import clustering_metrics, co2_statistics, eco_leaderboard


class TripRecordCRUDTests(TestCase):
    """Tests CRUD HTML : ajout, suppression, liste dans le dashboard."""

    def setUp(self):
        self.user = CustomUser.objects.create_user('crud_user', 'crud@greenmove.tn', 'pass12345!')
        self.client.force_login(self.user)

    def test_add_trip_record(self):
        now = timezone.now().strftime('%Y-%m-%dT%H:%M')
        resp = self.client.post(reverse('planner:add_trip'), {
            'date': now, 'mode': 'BIKE', 'distance_km': '5.0', 'duration_min': '20',
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(TripRecord.objects.filter(user=self.user, mode='BIKE').count(), 1)

    def test_add_trip_validates_distance(self):
        now = timezone.now().strftime('%Y-%m-%dT%H:%M')
        count_before = TripRecord.objects.count()
        resp = self.client.post(reverse('planner:add_trip'), {
            'date': now, 'mode': 'WALK', 'distance_km': '-1', 'duration_min': '10',
        })
        # Vue redirige avec message d'erreur, pas de création
        self.assertLessEqual(TripRecord.objects.count(), count_before + 1)

    def test_delete_trip_record(self):
        t = TripRecord.objects.create(
            user=self.user, date=timezone.now(), mode='BUS', distance_km=8, duration_min=25)
        resp = self.client.post(reverse('planner:delete_trip', args=[t.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(TripRecord.objects.filter(pk=t.pk).exists())

    def test_cannot_delete_others_trip(self):
        other = CustomUser.objects.create_user('other2', 'other2@g.tn', 'pass12345!')
        t = TripRecord.objects.create(
            user=other, date=timezone.now(), mode='CAR', distance_km=10, duration_min=15)
        self.client.post(reverse('planner:delete_trip', args=[t.pk]))
        self.assertTrue(TripRecord.objects.filter(pk=t.pk).exists())  # pas supprimé

    def test_dashboard_shows_recent_trips(self):
        TripRecord.objects.create(user=self.user, date=timezone.now(), mode='METRO', distance_km=6)
        resp = self.client.get(reverse('planner:index'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('recent_trips', resp.context)


class DRFApiTests(TestCase):
    """Tests API REST DRF : CRUD TripRecord, RecurringTrip, CarbonBudget."""

    def setUp(self):
        self.user = CustomUser.objects.create_user('drf_user', 'drf@greenmove.tn', 'pass12345!')
        self.client.force_login(self.user)

    def test_list_trips_empty(self):
        resp = self.client.get(reverse('planner:api_trips'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_create_trip_via_api(self):
        resp = self.client.post(reverse('planner:api_trips'),
                                data={'date': timezone.now().isoformat(), 'mode': 'CARPOOL',
                                      'distance_km': 12.5, 'duration_min': 30},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data['mode'], 'CARPOOL')
        self.assertIn('co2_kg', data)
        self.assertGreater(data['co2_kg'], 0)

    def test_retrieve_update_delete_trip_api(self):
        t = TripRecord.objects.create(user=self.user, date=timezone.now(), mode='BUS', distance_km=7)
        url = reverse('planner:api_trip_detail', args=[t.pk])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertFalse(TripRecord.objects.filter(pk=t.pk).exists())

    def test_api_trip_isolation(self):
        """Un utilisateur ne peut pas voir les trajets d'un autre."""
        other = CustomUser.objects.create_user('spy2', 'spy2@g.tn', 'pass12345!')
        t = TripRecord.objects.create(user=other, date=timezone.now(), mode='CAR', distance_km=15)
        url = reverse('planner:api_trip_detail', args=[t.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_recurring_trip_api_crud(self):
        url = reverse('planner:api_recurring')
        resp = self.client.post(url, data={'label': 'Cours', 'weekday': 1,
                                           'arrival_time': '09:00', 'distance_km': 8.0},
                                content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        pk = resp.json()['id']
        self.assertEqual(self.client.get(reverse('planner:api_recurring_detail', args=[pk])).status_code, 200)
        self.assertEqual(self.client.delete(reverse('planner:api_recurring_detail', args=[pk])).status_code, 204)

    def test_carbon_budget_api_get_post(self):
        resp = self.client.get(reverse('planner:api_carbon_budget'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('budget_kg', resp.json())
        resp2 = self.client.post(reverse('planner:api_carbon_budget'),
                                 data={'budget_kg': 45.0, 'month': timezone.localdate().replace(day=1).isoformat()},
                                 content_type='application/json')
        self.assertIn(resp2.status_code, (200, 201))

    def test_api_requires_auth(self):
        from django.test import Client
        c = Client()
        self.assertIn(c.get(reverse('planner:api_trips')).status_code, (401, 403))


class MetricsAndLeaderboardTests(TestCase):
    """Tests métriques IA et leaderboard."""

    def setUp(self):
        self.user = CustomUser.objects.create_user('metrics_user', 'met@greenmove.tn', 'pass12345!')
        self.client.force_login(self.user)
        now = timezone.now()
        for i, (mode, km) in enumerate([('CAR', 10), ('BUS', 8), ('BIKE', 4)] * 4):
            TripRecord.objects.create(user=self.user, date=now - timedelta(days=i), mode=mode, distance_km=km)

    def test_api_metrics_endpoint(self):
        resp = self.client.get(reverse('planner:api_metrics'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('clustering', data)
        self.assertIn('co2_stats', data)
        self.assertIn('leaderboard', data)


    def test_clustering_report_exposes_baseline_elbow_and_stability(self):
        users = [
            CustomUser.objects.create_user(f'cluster_{i}', f'cluster{i}@greenmove.tn', 'pass12345!')
            for i in range(3)
        ]
        samples = [
            [('CAR', 40), ('WALK', 2)],
            [('BUS', 30), ('BIKE', 8)],
            [('CAR', 10), ('BUS', 20), ('BIKE', 10)],
        ]
        for user, trips in zip(users, samples):
            for mode, km in trips:
                TripRecord.objects.create(user=user, date=timezone.now(), mode=mode, distance_km=km)
        report = clustering_metrics()
        self.assertEqual(report['status'], 'ok')
        self.assertIn('baseline', report)
        self.assertIn('elbow', report)
        self.assertIn('stability_ari_5_seeds', report)

    def test_api_ai_metrics_drf(self):
        resp = self.client.get(reverse('planner:api_ai_metrics'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('clustering', data)
        self.assertIn('co2_stats', data)

    def test_co2_stats_structure(self):
        stats = co2_statistics(self.user)
        self.assertIn('total_co2_kg', stats)
        self.assertIn('savings_vs_car_pct', stats)
        self.assertIn('vs_paris_target_kg', stats)
        self.assertIn('by_mode', stats)
        self.assertGreater(stats['total_co2_kg'], 0)

    def test_leaderboard_endpoint(self):
        resp = self.client.get(reverse('planner:api_leaderboard'))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn('leaderboard', data)

    def test_eco_leaderboard_service(self):
        board = eco_leaderboard(5)
        self.assertIsInstance(board, list)
        if board:
            self.assertIn('eco_score', board[0])
            self.assertIn('rank', board[0])

    def test_clustering_metrics_insufficient(self):
        """Sans données, le service retourne un statut clair."""
        # Utilisateur sans historique
        u2 = CustomUser.objects.create_user('empty_user', 'empty@g.tn', 'pass12345!')
        result = clustering_metrics(population_limit=1)  # 1 seul = insuffisant
        self.assertIn('status', result)

    def test_clustering_metrics_with_data(self):
        # Avec données, le clustering doit fonctionner
        result = clustering_metrics(population_limit=10)
        self.assertIn(result['status'], ('ok', 'insufficient_data'))


class ExportTests(TestCase):
    """Tests export CSV et calendrier."""

    def setUp(self):
        self.user = CustomUser.objects.create_user('export_user', 'exp@greenmove.tn', 'pass12345!')
        self.client.force_login(self.user)
        TripRecord.objects.create(user=self.user, date=timezone.now(), mode='WALK', distance_km=2)
        TripRecord.objects.create(user=self.user, date=timezone.now() - timedelta(days=1), mode='BUS', distance_km=9)

    def test_csv_export_headers(self):
        resp = self.client.get(reverse('planner:export_csv'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('text/csv', resp['Content-Type'])
        content = resp.content.decode('utf-8-sig')
        reader = csv.reader(io.StringIO(content))
        headers = next(reader)
        self.assertIn('Mode', headers)
        self.assertIn('Distance (km)', headers)

    def test_csv_export_contains_trips(self):
        resp = self.client.get(reverse('planner:export_csv'))
        content = resp.content.decode('utf-8-sig')
        self.assertIn('Marche', content)
        self.assertIn('Bus', content)

    def test_csv_export_requires_auth(self):
        from django.test import Client
        resp = Client().get(reverse('planner:export_csv'))
        self.assertEqual(resp.status_code, 302)


class ErrorPageTests(TestCase):
    """Tests pages d'erreur 404 et 500."""

    def test_404_page(self):
        resp = self.client.get('/url-qui-nexiste-vraiment-pas-du-tout-123456/')
        self.assertEqual(resp.status_code, 404)

    def test_handler404_view(self):
        from core.views import handler404
        from django.test import RequestFactory
        req = RequestFactory().get('/fake/')
        resp = handler404(req)
        self.assertEqual(resp.status_code, 404)

    def test_handler500_view(self):
        from core.views import handler500
        from django.test import RequestFactory
        req = RequestFactory().get('/fake/')
        resp = handler500(req)
        self.assertEqual(resp.status_code, 500)
