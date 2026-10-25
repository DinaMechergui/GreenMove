"""Tests IA MobilityMatch : métriques chiffrées, tâche Celery, page HTMX, sécurité d'accès."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .services import metrics
from . import tasks

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


class ClassificationMetricsTests(TestCase):
    def test_perfect_prediction(self):
        r = metrics.classification_metrics([1, 0, 1, 0], [1, 0, 1, 0])
        self.assertEqual((r['precision'], r['recall'], r['f1'], r['accuracy']), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(r['confusion'], {'tp': 2, 'fp': 0, 'fn': 0, 'tn': 2})

    def test_all_wrong_and_empty(self):
        r = metrics.classification_metrics([1, 1], [0, 0])
        self.assertEqual(r['f1'], 0.0)
        self.assertEqual(metrics.classification_metrics([], [])['accuracy'], 0.0)


class MatcherEvaluationTests(TestCase):
    def test_dataset_is_balanced_and_reproducible(self):
        a = metrics.build_match_dataset(40)
        b = metrics.build_match_dataset(40)
        self.assertEqual(sum(d['label'] for d in a), 20)
        self.assertEqual([d['origin'] for d in a], [d['origin'] for d in b])

    def test_model_beats_baseline(self):
        r = metrics.evaluate_matcher(n=120)
        self.assertGreater(r['model']['f1'], r['baseline']['f1'])
        self.assertGreater(r['model']['accuracy'], 0.8)
        self.assertGreaterEqual(r['threshold'], 20)

    def test_clustering_beats_baseline(self):
        r = metrics.evaluate_clustering()
        self.assertGreater(r['model']['silhouette'], r['baseline']['silhouette'])
        self.assertGreaterEqual(r['model']['ari'], 0.9)


@override_settings(CACHES=LOCMEM)
class AsyncTaskTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_task_stores_report(self):
        with mock.patch('match.services.metrics.full_report', return_value={'matching': {}, 'clustering': {}}):
            self.assertEqual(tasks.evaluate_ai_async(), 'done')
        self.assertIn('duration_s', cache.get(tasks.METRICS_CACHE_KEY))
        self.assertEqual(cache.get(tasks.METRICS_STATUS_KEY), 'done')

    def test_task_error_is_flagged(self):
        with mock.patch('match.services.metrics.full_report', side_effect=RuntimeError):
            self.assertEqual(tasks.evaluate_ai_async(), 'error')
        self.assertEqual(cache.get(tasks.METRICS_STATUS_KEY), 'error')

    def test_refresh_groups_task(self):
        self.assertEqual(tasks.refresh_ride_groups(), 0)


@override_settings(CACHES=LOCMEM)
class MetricsViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = get_user_model().objects.create_user('dina', 'd@x.tn', 'pass12345!')

    def test_anonymous_is_redirected(self):
        for name in ('match:ai_metrics', 'match:ai_metrics_status'):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse('accounts:login'), resp['Location'])

    def test_page_launches_task_and_polls(self):
        self.client.force_login(self.user)
        with mock.patch('match.tasks.evaluate_ai_async.delay') as delay:
            resp = self.client.get(reverse('match:ai_metrics'))
        delay.assert_called_once()
        self.assertContains(resp, 'hx-get')
        self.assertContains(resp, 'aria-live')
        status = self.client.get(reverse('match:ai_metrics_status'))
        self.assertContains(status, 'every 2s')

    def test_broker_down_is_reported_without_sync_fallback(self):
        self.client.force_login(self.user)
        with mock.patch('match.tasks.evaluate_ai_async.delay', side_effect=ConnectionError), \
             mock.patch('match.services.metrics.full_report') as report:
            self.client.post(reverse('match:ai_metrics'))
        resp = self.client.get(reverse('match:ai_metrics_status'))
        self.assertContains(resp, 'alert-danger')
        report.assert_not_called()

    def test_error_state_rendered(self):
        self.client.force_login(self.user)
        cache.set(tasks.METRICS_STATUS_KEY, 'error')
        self.assertContains(self.client.get(reverse('match:ai_metrics_status')), 'alert-danger')


class GroupsApiRobustnessTests(TestCase):
    def test_invalid_params_return_400(self):
        resp = self.client.get(reverse('match:api_groups'), {'eps': 'abc'})
        self.assertEqual(resp.status_code, 400)

    def test_valid_params_return_200(self):
        resp = self.client.get(reverse('match:api_groups'), {'eps': '1500'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()['groups'], [])
