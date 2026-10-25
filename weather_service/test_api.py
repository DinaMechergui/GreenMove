from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase
from django.urls import reverse
from rest_framework.test import APIClient

from .services import WeatherAPIError

A = 'weather_service.api.services.'


class WeatherApiTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def get(self, name, **params):
        return self.client.get(reverse(f'weather_api:{name}'), params)

    @patch(A + 'get_comfort_score', return_value={'score': 80, 'label': 'excellent'})
    def test_comfort_ok(self, m):
        r = self.get('comfort', lat=36.8, lon=10.2, mode='bike', hours_ahead=3)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['score'], 80)
        m.assert_called_once_with(36.8, 10.2, 3, 'bike')

    @patch(A + 'get_comfort_score', return_value={})
    def test_comfort_defaults_to_tunis(self, m):
        self.get('comfort')
        m.assert_called_once_with(36.8065, 10.1815, 0, 'walk')

    def test_comfort_bad_params_400(self):
        for params in ({'mode': 'car'}, {'lat': 'x'}, {'lat': 95}, {'hours_ahead': 99},
                       {'hours_ahead': 'abc'}):
            r = self.get('comfort', **params)
            self.assertEqual(r.status_code, 400, params)
            self.assertIn('error', r.json())

    @patch(A + 'rain_alert', return_value={'alert': True, 'minutes': 15, 'message': 'x'})
    def test_rain_alert_ok(self, _m):
        self.assertTrue(self.get('rain_alert').json()['alert'])

    @patch(A + 'get_air_quality', side_effect=WeatherAPIError('down'))
    def test_air_quality_503(self, _m):
        r = self.get('air_quality')
        self.assertEqual(r.status_code, 503)
        self.assertIn('indisponible', r.json()['error'])

    @patch(A + 'best_hours', return_value=[{'time': 't', 'score': 90}])
    def test_best_hours_ok(self, _m):
        body = self.get('best_hours', mode='walk').json()
        self.assertEqual(body['mode'], 'walk')
        self.assertEqual(body['hours'][0]['score'], 90)

    @patch('weather_service.services.requests.get',
           side_effect=requests.ConnectionError('offline'))
    def test_network_failure_end_to_end_503(self, _get):
        """Aucun mock du service : seul requests est simulé (pas d'appel réseau réel)."""
        self.assertEqual(self.get('rain_alert').status_code, 503)

    @patch('weather_service.services.requests.get')
    def test_air_quality_end_to_end(self, get):
        get.return_value = MagicMock(status_code=200, json=lambda: {
            'current': {'european_aqi': 30, 'pm10': 10, 'pm2_5': 5}})
        body = self.get('air_quality').json()
        self.assertEqual(body['label'], 'bonne')
        self.assertFalse(body['alert'])
