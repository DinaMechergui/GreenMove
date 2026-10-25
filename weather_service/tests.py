from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from . import services


class ComfortScoreTests(SimpleTestCase):
    def test_ideal_conditions(self):
        self.assertEqual(services.comfort_score(21, 0, 5, 3), 100)

    def test_rain_lowers_score(self):
        self.assertLess(services.comfort_score(21, 2, 5, 3),
                        services.comfort_score(21, 0, 5, 3))

    def test_bike_penalizes_wind_more(self):
        self.assertLess(services.comfort_score(20, 0, 35, 3, mode='bike'),
                        services.comfort_score(20, 0, 35, 3, mode='walk'))

    def test_score_is_bounded(self):
        self.assertEqual(services.comfort_score(-10, 20, 90, 12, 100), 0)


class RainAlertTests(SimpleTestCase):
    def setUp(self):
        cache.clear()

    @patch('weather_service.services._get')
    def test_rain_coming(self, mock_get):
        mock_get.return_value = {'minutely_15': {
            'time': ['t0', 't1', 't2'], 'precipitation': [0.0, 0.0, 0.6]}}
        res = services.rain_alert(36.8, 10.18)
        self.assertTrue(res['alert'])
        self.assertEqual(res['minutes'], 30)

    @patch('weather_service.services._get')
    def test_no_rain(self, mock_get):
        mock_get.return_value = {'minutely_15': {'time': ['t0'], 'precipitation': [0.0]}}
        self.assertFalse(services.rain_alert(36.8, 10.18)['alert'])


class AirQualityTests(SimpleTestCase):
    @patch('weather_service.services._get')
    def test_alert_when_poor(self, mock_get):
        mock_get.return_value = {'current': {'european_aqi': 75, 'pm10': 40, 'pm2_5': 22}}
        res = services.get_air_quality()
        self.assertTrue(res['alert'])
        self.assertEqual(res['label'], 'médiocre')