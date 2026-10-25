from datetime import date
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from traffic.models import MonitoringPoint


class TrafficViewTests(TestCase):
    def setUp(self):
        self.a = MonitoringPoint.objects.create(name='Ariana', latitude=36.86, longitude=10.19)
        self.b = MonitoringPoint.objects.create(name='Lac 2', latitude=36.84, longitude=10.27)

    def test_map_page_loads_200(self):
        r = self.client.get(reverse('traffic:index'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'traffic-map')
        self.assertContains(r, 'Données de trafic simulées')

    def test_best_time_page_loads_200(self):
        r = self.client.get(reverse('traffic:best_time'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Point de départ')

    @patch('traffic.best_time.service.base_duration_minutes', return_value={'minutes': 20, 'source': 'test'})
    @patch('traffic.best_time.service.predict_congestion', return_value=0.3)
    @patch('traffic.best_time.service._rain_by_hour', return_value={})
    def test_best_time_submission_loads_result(self, _rain, _pred, _base):
        params = {
            'origin': self.a.id,
            'destination': self.b.id,
            'day': date.today().isoformat(),
            'start_time': '07:00',
            'end_time': '09:00',
        }
        r = self.client.get(reverse('traffic:best_time'), params)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'best-time-results-container')

    @patch('traffic.best_time.service.base_duration_minutes', return_value={'minutes': 20, 'source': 'test'})
    @patch('traffic.best_time.service.predict_congestion', return_value=0.3)
    @patch('traffic.best_time.service._rain_by_hour', return_value={})
    def test_best_time_htmx_partial(self, _rain, _pred, _base):
        params = {
            'origin': self.a.id,
            'destination': self.b.id,
            'day': date.today().isoformat(),
            'start_time': '07:00',
            'end_time': '09:00',
        }
        r = self.client.get(reverse('traffic:best_time'), params, HTTP_HX_REQUEST='true')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'bestTimeChart')
        # Pas de html complet dans la réponse HTMX
        self.assertNotContains(r, '<!DOCTYPE html>')

    def test_history_page_loads_200(self):
        r = self.client.get(reverse('traffic:history'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'historyChart')

    def test_about_data_page_loads_200(self):
        r = self.client.get(reverse('traffic:about_data'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Transparence sur les données de trafic')
        self.assertContains(r, 'Ariana')
