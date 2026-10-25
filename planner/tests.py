"""Tests EcoPlanner."""
from datetime import time, timedelta

from django.test import TestCase
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from .models import RecurringTrip, TripRecord
from .services import planning
from .services.emissions import co2_kg


class PlannerTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user('amine', 'amine@greenmove.tn', 'pass12345!')
        now = timezone.now()
        for i, (mode, km) in enumerate([('CAR', 10), ('CAR', 12), ('BUS', 8), ('BIKE', 4)] * 3):
            TripRecord.objects.create(user=self.user, date=now - timedelta(days=i * 3), mode=mode,
                                      distance_km=km, duration_min=20)

    def test_co2_saved_on_record(self):
        self.assertAlmostEqual(TripRecord.objects.filter(mode='CAR').first().co2_kg,
                               co2_kg('CAR', TripRecord.objects.filter(mode='CAR').first().distance_km))

    def test_weekly_history_and_profile(self):
        self.assertTrue(planning.weekly_history(self.user))
        profile = planning.weekly_profile(self.user)
        self.assertIn('CAR', profile['modes'])
        self.assertEqual(len(profile['co2_by_weekday']), 7)

    def test_optimizer_avoids_car_for_short_trip(self):
        best = planning.score_options(2.0)[0]
        self.assertIn(best['mode'], ('WALK', 'BIKE'))
        self.assertNotIn('WALK', [o['mode'] for o in planning.score_options(10.0)])

    def test_rain_penalises_soft_modes(self):
        dry = {o['mode']: o['score'] for o in planning.score_options(3.0)}
        wet = {o['mode']: o['score'] for o in planning.score_options(3.0, bad_weather=True)}
        self.assertGreater(wet['BIKE'], dry['BIKE'])

    def test_plan_and_simulation(self):
        RecurringTrip.objects.create(user=self.user, label='Cours', weekday=0,
                                     arrival_time=time(9, 0), distance_km=8)
        plan = planning.optimize_week(self.user)
        self.assertEqual(len(plan['plan']), 1)
        self.assertGreaterEqual(plan['co2_saved_kg'], 0)
        self.assertGreaterEqual(planning.simulate_impact(self.user, 1, plan)['co2_saved_kg'], 0)

    def test_ics_roundtrip(self):
        RecurringTrip.objects.create(user=self.user, label='Réunion', weekday=2,
                                     arrival_time=time(14, 30), distance_km=6)
        ics = planning.export_ics(self.user)
        self.assertIn('BEGIN:VCALENDAR', ics)
        RecurringTrip.objects.all().delete()
        self.assertEqual(planning.import_ics(self.user, ics), 1)

    def test_classification_and_budget(self):
        self.assertIn(planning.classify_user(self.user)['type'], ('driver', 'mixed', 'soft'))
        self.assertEqual(planning.carbon_budget_status(self.user)['budget_kg'], 60.0)

    def test_dashboard_and_api(self):
        self.assertEqual(self.client.get(reverse('planner:index')).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('planner:index')).status_code, 200)
        self.assertEqual(self.client.get(reverse('planner:api_plan')).status_code, 200)
        self.assertEqual(self.client.get(reverse('planner:export_calendar')).status_code, 200)


@override_settings(CACHES={'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}})
class PlannerAsyncReportTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = CustomUser.objects.create_user('report_user', 'report@greenmove.tn', 'pass12345!')

    def test_background_task_stores_plan_report_and_duration(self):
        from unittest.mock import patch
        from . import tasks

        plan = {'plan': [], 'co2_saved_kg': 0.0}
        with patch('planner.tasks.planning.optimize_week', return_value=plan), \
             patch('planner.services.report.render_report', return_value=(b'pdf', 'application/pdf', 'pdf')):
            self.assertEqual(tasks.generate_plan_and_report_async(self.user.pk), 'ready')
        result = cache.get(tasks.REPORT_RESULT_KEY.format(self.user.pk))
        self.assertEqual(result['plan'], plan)
        self.assertEqual(result['report'], b'pdf')
        self.assertIn('duration_ms', result)
        self.assertEqual(cache.get(tasks.REPORT_STATUS_KEY.format(self.user.pk))['state'], 'ready')

    def test_report_download_is_user_scoped(self):
        from .tasks import REPORT_RESULT_KEY

        cache.set(REPORT_RESULT_KEY.format(self.user.pk), {
            'report': b'own', 'mimetype': 'application/pdf', 'extension': 'pdf', 'plan': {},
        })
        self.client.force_login(self.user)
        response = self.client.get(reverse('planner:download_report'))
        self.assertEqual(response.content, b'own')
        other = CustomUser.objects.create_user('other_report', 'other@greenmove.tn', 'pass12345!')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('planner:download_report')).status_code, 202)

    def test_unavailable_worker_is_reported_without_running_task_inline(self):
        from unittest.mock import patch

        self.client.force_login(self.user)
        with patch('planner.views.generate_plan_and_report_async') as task:
            task.delay.side_effect = ConnectionError
            response = self.client.post(reverse('planner:generate_report'))
        self.assertEqual(response.status_code, 302)
        task.assert_not_called()
        self.assertEqual(cache.get('planner:bundle:status:{}'.format(self.user.pk))['state'], 'error')
