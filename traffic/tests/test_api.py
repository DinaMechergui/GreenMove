from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from traffic.ml.predict import ModelNotTrained, predict_batch
from traffic.models import MonitoringPoint, TrafficSnapshot
from weather_service.services import WeatherAPIError

V = 'traffic.api.views.'


class ApiTestCase(TestCase):
    def setUp(self):
        cache.clear()  # réinitialise aussi les compteurs de throttling
        self.client = APIClient()
        self.a = MonitoringPoint.objects.create(name='Lac 2', latitude=36.84, longitude=10.27)
        self.b = MonitoringPoint.objects.create(name='Bardo', latitude=36.81, longitude=10.13)
        self.off = MonitoringPoint.objects.create(name='Off', latitude=36.8, longitude=10.1,
                                                  is_active=False)

    def get(self, name, **params):
        return self.client.get(reverse(f'traffic_api:{name}'), params)


class PointsApiTests(ApiTestCase):
    def test_lists_active_points_only(self):
        r = self.get('points')
        self.assertEqual(r.status_code, 200)
        self.assertEqual({p['name'] for p in r.json()}, {'Lac 2', 'Bardo'})
        self.assertEqual(set(r.json()[0]), {'id', 'name', 'lat', 'lon'})


@patch(V + 'predict_congestion', return_value=0.65)
class ForecastApiTests(ApiTestCase):
    def test_ok(self, _pred):
        r = self.get('forecast', point=self.a.id, datetime='2026-10-26T08:00')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['congestion'], 0.65)
        self.assertEqual(body['level'], 'dense')
        self.assertEqual(body['level_code'], 'dense')
        self.assertTrue(body['datetime'].startswith('2026-10-26T08:00'))

    def test_default_datetime_is_now(self, _pred):
        self.assertEqual(self.get('forecast', point=self.a.id).status_code, 200)

    def test_missing_point_400(self, _pred):
        r = self.get('forecast')
        self.assertEqual(r.status_code, 400)
        self.assertIn('error', r.json())

    def test_point_not_integer_400(self, _pred):
        self.assertEqual(self.get('forecast', point='abc').status_code, 400)

    def test_unknown_point_404(self, _pred):
        r = self.get('forecast', point=99999)
        self.assertEqual(r.status_code, 404)
        self.assertIn('introuvable', r.json()['error'])

    def test_inactive_point_404(self, _pred):
        self.assertEqual(self.get('forecast', point=self.off.id).status_code, 404)

    def test_bad_datetime_400(self, _pred):
        r = self.get('forecast', point=self.a.id, datetime='demain')
        self.assertEqual(r.status_code, 400)

    def test_model_not_trained_503(self, pred):
        pred.side_effect = ModelNotTrained()
        r = self.get('forecast', point=self.a.id)
        self.assertEqual(r.status_code, 503)
        self.assertIn('Modèle non entraîné', r.json()['error'])


class HeatmapApiTests(ApiTestCase):
    points = [{'point': 'Lac 2', 'lat': 36.84, 'lon': 10.27, 'congestion': 0.2},
              {'point': 'Bardo', 'lat': 36.81, 'lon': 10.13, 'congestion': 0.85}]

    @patch(V + 'get_hourly_forecast')
    @patch(V + 'predict_all_points')
    def test_ok_with_rain(self, pred, forecast):
        pred.return_value = [dict(p) for p in self.points]
        forecast.return_value = [{'time': '2026-10-26T08:00', 'precipitation_mm': 1.2}]
        r = self.get('heatmap', datetime='2026-10-26T08:30')
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body['precipitation_mm'], 1.2)
        self.assertTrue(body['weather_available'])
        self.assertEqual([p['level'] for p in body['points']], ['fluide', 'bloqué'])
        pred.assert_called_once()
        self.assertEqual(pred.call_args.kwargs['precipitation_mm'], 1.2)

    @patch(V + 'get_hourly_forecast', side_effect=WeatherAPIError('down'))
    @patch(V + 'predict_all_points')
    def test_weather_down_still_ok(self, pred, _f):
        pred.return_value = [dict(p) for p in self.points]
        body = self.get('heatmap').json()
        self.assertFalse(body['weather_available'])
        self.assertEqual(body['precipitation_mm'], 0.0)

    @patch(V + 'get_hourly_forecast', return_value=[])
    @patch(V + 'predict_all_points', side_effect=ModelNotTrained())
    def test_model_not_trained_503(self, _p, _f):
        self.assertEqual(self.get('heatmap').status_code, 503)

    def test_bad_datetime_400(self):
        self.assertEqual(self.get('heatmap', datetime='2026-13-45').status_code, 400)


class BestTimeApiTests(ApiTestCase):
    def params(self, **kw):
        p = {'origin': self.a.id, 'destination': self.b.id,
             'start': '2026-10-26T07:00', 'end': '2026-10-26T09:00'}
        p.update(kw)
        return p

    @patch(V + 'best_departure')
    def test_ok(self, bd):
        bd.return_value = {'message': 'Partez à 07:00', 'options': []}
        r = self.get('best_time', **self.params(step=30))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['message'], 'Partez à 07:00')
        args = bd.call_args.args
        self.assertEqual((args[0], args[1], args[4]), (self.a.id, self.b.id, 30))

    def test_start_after_end_400(self):
        r = self.get('best_time', **self.params(start='2026-10-26T10:00'))
        self.assertEqual(r.status_code, 400)
        self.assertIn('antérieure', r.json()['error'])

    def test_range_over_12h_400(self):
        r = self.get('best_time', **self.params(end='2026-10-26T20:00'))
        self.assertEqual(r.status_code, 400)
        self.assertIn('12 heures', r.json()['error'])

    def test_step_bounds_400(self):
        for step in (4, 61, 'x'):
            self.assertEqual(self.get('best_time', **self.params(step=step)).status_code, 400, step)

    def test_same_points_400(self):
        self.assertEqual(self.get('best_time', **self.params(destination=self.a.id)).status_code, 400)

    def test_missing_start_400(self):
        p = self.params()
        del p['start']
        self.assertEqual(self.get('best_time', **p).status_code, 400)

    def test_unknown_point_404(self):
        self.assertEqual(self.get('best_time', **self.params(origin=424242)).status_code, 404)

    @patch(V + 'best_departure', side_effect=ModelNotTrained())
    def test_model_not_trained_503(self, _bd):
        self.assertEqual(self.get('best_time', **self.params()).status_code, 503)


class HistoryApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        for i in range(8):
            TrafficSnapshot.objects.create(point=self.a, timestamp=now - timedelta(hours=i * 3),
                                           current_speed=30, free_flow_speed=50, congestion=0.4)
        TrafficSnapshot.objects.create(point=self.a, timestamp=now - timedelta(days=5),
                                       current_speed=30, free_flow_speed=50, congestion=0.4)

    @patch(V + 'predict_batch', side_effect=lambda rows: [0.5] * len(rows))
    def test_ok_with_predictions(self, _p):
        r = self.get('history', point=self.a.id, days=1)
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body['model_available'])
        self.assertEqual(len(body['snapshots']), 8)  # le snapshot de J-5 est exclu
        self.assertEqual(body['snapshots'][0]['predicted'], 0.5)
        self.assertLess(body['snapshots'][0]['timestamp'], body['snapshots'][-1]['timestamp'])

    @patch(V + 'predict_batch', side_effect=ModelNotTrained())
    def test_model_missing_still_returns_history(self, _p):
        body = self.get('history', point=self.a.id).json()
        self.assertFalse(body['model_available'])
        self.assertIsNone(body['snapshots'][0]['predicted'])

    def test_no_snapshot(self):
        body = self.get('history', point=self.b.id).json()
        self.assertEqual(body['snapshots'], [])

    def test_days_out_of_range_400(self):
        self.assertEqual(self.get('history', point=self.a.id, days=30).status_code, 400)
        self.assertEqual(self.get('history', point=self.a.id, days=0).status_code, 400)

    def test_unknown_point_404(self):
        self.assertEqual(self.get('history', point=123456).status_code, 404)


class PredictBatchTests(TestCase):
    def test_empty_rows(self):
        self.assertEqual(predict_batch([]), [])
