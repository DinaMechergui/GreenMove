"""Tests : signal budget, rapport, explications, tâches, i18n, throttling."""
from datetime import time, timedelta
from unittest import mock

from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone, translation

from accounts.models import CustomUser
from .models import CarbonBudget, RecurringTrip, TripRecord
from .services import planning
from .services.explain import explain_plan
from .services.report import render_report
from . import tasks
from .signals import GAUGE_CACHE_KEY


class PlannerExtraTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user('lina', 'lina@greenmove.tn', 'pass12345!', first_name='Lina')
        RecurringTrip.objects.create(user=self.user, label='Cours', weekday=1,
                                     arrival_time=time(9, 0), distance_km=9)

    def test_signal_updates_gauge_and_sends_alert_once(self):
        CarbonBudget.objects.create(user=self.user, month=timezone.localdate().replace(day=1), budget_kg=10)
        TripRecord.objects.create(user=self.user, date=timezone.now(), mode='CAR', distance_km=50)  # 9.6 kg
        self.assertIsNotNone(cache.get(GAUGE_CACHE_KEY.format(self.user.pk)))
        self.assertEqual(len(mail.outbox), 1)
        TripRecord.objects.create(user=self.user, date=timezone.now(), mode='CAR', distance_km=5)
        self.assertEqual(len(mail.outbox), 2)  # passage 80 % -> 100 %
        TripRecord.objects.create(user=self.user, date=timezone.now(), mode='CAR', distance_km=1)
        self.assertEqual(len(mail.outbox), 2)  # pas de doublon

    def test_report_always_renders(self):
        content, mimetype, ext = render_report(self.user)
        self.assertIn(ext, ('pdf', 'html'))
        self.assertTrue(content)

    def test_report_falls_back_to_html_without_weasyprint(self):
        with mock.patch.dict('sys.modules', {'weasyprint': None}):
            _, mimetype, ext = render_report(self.user)
        self.assertEqual((mimetype, ext), ('text/html', 'html'))

    def test_weekly_task_sends_email(self):
        self.assertEqual(tasks.send_weekly_reports(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(len(mail.outbox[0].attachments), 1)

    def test_explanations_fallback_to_templates(self):
        with override_settings(LLM_PROVIDER='gemini', GEMINI_API_KEY='x'), \
                mock.patch('planner.services.explain.requests.post', side_effect=Exception('down')):
            data = explain_plan(planning.optimize_week(self.user))
        self.assertEqual(data['source'], 'template')
        self.assertEqual(len(data['items']), 1)

    def test_explanations_use_llm_when_available(self):
        resp = mock.Mock()
        resp.json.return_value = {'response': 'Super plan !'}
        with override_settings(LLM_PROVIDER='ollama'), \
                mock.patch('planner.services.explain.requests.post', return_value=resp):
            data = explain_plan(planning.optimize_week(self.user))
        self.assertEqual((data['source'], data['summary']), ('llm', 'Super plan !'))

    def test_auto_weather_rain(self):
        self.client.force_login(self.user)
        rainy = {'description': 'Pluie modérée', 'is_fallback': False}
        with mock.patch('core.services.weather.get_tunis_weather', return_value=rainy):
            r = self.client.get(reverse('planner:api_plan'))
        self.assertEqual(r.status_code, 200)
        with mock.patch('core.services.weather.get_tunis_weather', return_value=rainy):
            self.assertTrue(self.client.get(reverse('planner:index')).context['rain'])
        # forçage explicite
        with mock.patch('core.services.weather.get_tunis_weather', return_value=rainy):
            self.assertFalse(self.client.get(reverse('planner:index') + '?rain=0').context['rain'])

    def test_translations_loaded(self):
        with translation.override('en'):
            self.assertEqual(translation.gettext('Plan de la semaine'), 'Weekly plan')
        with translation.override('ar'):
            self.assertEqual(translation.gettext('Plan de la semaine'), 'خطة الأسبوع')

    def test_api_budget_endpoint(self):
        self.client.force_login(self.user)
        data = self.client.get(reverse('planner:api_budget')).json()
        self.assertIn('projected_kg', data)

    def test_login_page_without_google(self):
        r = self.client.get(reverse('accounts:login'))
        self.assertNotContains(r, 'Continuer avec Google')
        with override_settings(GOOGLE_LOGIN_ENABLED=True):
            r = self.client.get(reverse('accounts:login'))
        self.assertContains(r, 'Continuer avec Google')

    def test_api_throttling_configured(self):
        from django.conf import settings
        self.assertIn('anon', settings.REST_FRAMEWORK['DEFAULT_THROTTLE_RATES'])
