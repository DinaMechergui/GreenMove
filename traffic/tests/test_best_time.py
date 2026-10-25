from datetime import datetime
from unittest.mock import patch

from django.test import TestCase

from traffic.best_time import best_departure
from traffic.best_time.routing import haversine_km
from traffic.models import MonitoringPoint


class RoutingTests(TestCase):
    def test_haversine_zero(self):
        self.assertAlmostEqual(haversine_km(36.8, 10.1, 36.8, 10.1), 0)

    def test_haversine_tunis_ariana(self):
        d = haversine_km(36.8065, 10.1815, 36.8665, 10.1647)
        self.assertTrue(5 < d < 9)


class BestTimeTests(TestCase):
    def setUp(self):
        self.a = MonitoringPoint.objects.create(name='A', latitude=36.80, longitude=10.18)
        self.b = MonitoringPoint.objects.create(name='B', latitude=36.85, longitude=10.27)

    @patch('traffic.best_time.service._rain_by_hour', return_value={})
    @patch('traffic.best_time.service.base_duration_minutes',
           return_value={'minutes': 20, 'source': 'test'})
    @patch('traffic.best_time.service.predict_congestion')
    def test_picks_lowest_congestion(self, mock_pred, _base, _rain):
        mock_pred.side_effect = lambda pid, t, mm: 0.8 if t.hour >= 8 else 0.2
        res = best_departure(self.a.id, self.b.id,
                             datetime(2026, 10, 26, 7, 0), datetime(2026, 10, 26, 8, 30))
        self.assertTrue(res['best']['departure'].endswith('07:00'))
        self.assertGreater(res['time_saved_min'], 0)