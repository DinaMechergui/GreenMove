"""Tests automatisés pour le CRUD, les formulaires et les permissions du module Traffic."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from traffic.forms import MonitoringPointForm, TrafficSnapshotForm
from traffic.models import MonitoringPoint, TrafficSnapshot

User = get_user_model()


class TrafficFormTests(TestCase):
    """Validation stricte des formulaires côté serveur."""

    def test_point_valid_tunisia_coords(self):
        form = MonitoringPointForm(data={
            'name': 'Lac 1',
            'latitude': 36.83,
            'longitude': 10.23,
            'profile': 'am_heavy',
            'is_active': True,
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_point_rejects_out_of_bounds_coords(self):
        # Latitude hors Tunisie (>38)
        form1 = MonitoringPointForm(data={
            'name': 'Paris',
            'latitude': 48.85,
            'longitude': 10.23,
            'profile': 'am_heavy',
        })
        self.assertFalse(form1.is_valid())
        self.assertIn('latitude', form1.errors)

        # Longitude hors Tunisie (>12)
        form2 = MonitoringPointForm(data={
            'name': 'Rome',
            'latitude': 36.83,
            'longitude': 12.5,
            'profile': 'am_heavy',
        })
        self.assertFalse(form2.is_valid())
        self.assertIn('longitude', form2.errors)

    def test_snapshot_valid(self):
        point = MonitoringPoint.objects.create(name='Avenue Bourguiba', latitude=36.80, longitude=10.18)
        # vitesse fluide = 50, actuelle = 25 => congestion attendue = 0.5
        form = TrafficSnapshotForm(data={
            'point': point.id,
            'timestamp': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'current_speed': 25.0,
            'free_flow_speed': 50.0,
            'congestion': 0.50,
            'precipitation_mm': 0.0,
            'is_holiday': False,
            'source': 'synthetic',
        })
        self.assertTrue(form.is_valid(), form.errors)

    def test_snapshot_rejects_congestion_out_of_range(self):
        point = MonitoringPoint.objects.create(name='P1', latitude=36.80, longitude=10.18)
        form = TrafficSnapshotForm(data={
            'point': point.id,
            'timestamp': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'current_speed': 30.0,
            'free_flow_speed': 50.0,
            'congestion': 5.0,  # Congestion = 5 interdite
            'precipitation_mm': 0.0,
            'source': 'synthetic',
        })
        self.assertFalse(form.is_valid())
        self.assertIn('congestion', form.errors)

    def test_snapshot_rejects_incoherent_speeds_and_congestion(self):
        point = MonitoringPoint.objects.create(name='P2', latitude=36.80, longitude=10.18)
        # Vitesse actuelle > 110% de vitesse fluide
        form1 = TrafficSnapshotForm(data={
            'point': point.id,
            'timestamp': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'current_speed': 80.0,
            'free_flow_speed': 50.0,
            'congestion': 0.1,
            'precipitation_mm': 0.0,
            'source': 'synthetic',
        })
        self.assertFalse(form1.is_valid())
        self.assertIn('current_speed', form1.errors)

        # Incohérence formule : current 40, free 50 => congestion = 0.20, mais saisie 0.85
        form2 = TrafficSnapshotForm(data={
            'point': point.id,
            'timestamp': timezone.now().strftime('%Y-%m-%dT%H:%M'),
            'current_speed': 40.0,
            'free_flow_speed': 50.0,
            'congestion': 0.85,
            'precipitation_mm': 0.0,
            'source': 'synthetic',
        })
        self.assertFalse(form2.is_valid())
        self.assertIn('congestion', form2.errors)


class TrafficCrudAuthAndPermissionTests(TestCase):
    """Vérification de l'authentification et du contrôle d'accès effectif par rôle."""

    def setUp(self):
        self.user_without_perms = User.objects.create_user(
            username='citizen_user', password='password123', email='citizen@greenmove.tn'
        )
        self.user_with_perms = User.objects.create_user(
            username='admin_traffic', password='password123', email='admin_traffic@greenmove.tn'
        )
        # Attribution de toutes les permissions traffic à l'utilisateur autorisé
        perms = Permission.objects.filter(content_type__app_label='traffic')
        self.user_with_perms.user_permissions.set(perms)

        self.point = MonitoringPoint.objects.create(
            name='Point Test Initial', latitude=36.84, longitude=10.27, profile='am_heavy'
        )
        self.snapshot = TrafficSnapshot.objects.create(
            point=self.point, current_speed=25.0, free_flow_speed=50.0, congestion=0.5
        )

    def test_anonymous_redirected_to_login(self):
        urls = [
            reverse('traffic:point_list'),
            reverse('traffic:point_detail', kwargs={'pk': self.point.pk}),
            reverse('traffic:point_create'),
            reverse('traffic:point_update', kwargs={'pk': self.point.pk}),
            reverse('traffic:point_delete', kwargs={'pk': self.point.pk}),
            reverse('traffic:snapshot_list'),
            reverse('traffic:snapshot_detail', kwargs={'pk': self.snapshot.pk}),
            reverse('traffic:snapshot_create'),
            reverse('traffic:snapshot_update', kwargs={'pk': self.snapshot.pk}),
            reverse('traffic:snapshot_delete', kwargs={'pk': self.snapshot.pk}),
        ]
        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 302, f"Échec redirection pour {url}")
            self.assertIn('/accounts/login/', response.url)

    def test_authenticated_user_without_perms_gets_403_on_modifications(self):
        self.client.login(username='citizen_user', password='password123')

        # Vues de lecture autorisées (200)
        self.assertEqual(self.client.get(reverse('traffic:point_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('traffic:point_detail', kwargs={'pk': self.point.pk})).status_code, 200)
        self.assertEqual(self.client.get(reverse('traffic:snapshot_list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('traffic:snapshot_detail', kwargs={'pk': self.snapshot.pk})).status_code, 200)

        # Vues de modification interdites (403 Forbidden)
        protected_urls = [
            reverse('traffic:point_create'),
            reverse('traffic:point_update', kwargs={'pk': self.point.pk}),
            reverse('traffic:point_delete', kwargs={'pk': self.point.pk}),
            reverse('traffic:snapshot_create'),
            reverse('traffic:snapshot_update', kwargs={'pk': self.snapshot.pk}),
            reverse('traffic:snapshot_delete', kwargs={'pk': self.snapshot.pk}),
        ]
        for url in protected_urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 403, f"Accès non refusé (attendu 403) pour {url}")
            # Tentative POST également refusée
            post_response = self.client.post(url, {})
            self.assertEqual(post_response.status_code, 403, f"POST non refusé (attendu 403) pour {url}")

    def test_authorized_user_can_create_update_delete_point(self):
        self.client.login(username='admin_traffic', password='password123')

        # 1. Création
        create_url = reverse('traffic:point_create')
        post_data = {
            'name': 'Nouveau Rond-Point Lac 2',
            'latitude': 36.8392,
            'longitude': 10.2447,
            'profile': 'center',
            'is_active': True,
        }
        res = self.client.post(create_url, post_data)
        self.assertEqual(res.status_code, 302)
        new_point = MonitoringPoint.objects.get(name='Nouveau Rond-Point Lac 2')
        self.assertRedirects(res, reverse('traffic:point_detail', kwargs={'pk': new_point.pk}))

        # 2. Modification
        update_url = reverse('traffic:point_update', kwargs={'pk': new_point.pk})
        post_data['name'] = 'Rond-Point Lac 2 Modifié'
        res_update = self.client.post(update_url, post_data)
        self.assertEqual(res_update.status_code, 302)
        new_point.refresh_from_db()
        self.assertEqual(new_point.name, 'Rond-Point Lac 2 Modifié')

        # 3. Suppression
        delete_url = reverse('traffic:point_delete', kwargs={'pk': new_point.pk})
        del_confirm = self.client.get(delete_url)
        self.assertEqual(del_confirm.status_code, 200)
        self.assertContains(del_confirm, 'Rond-Point Lac 2 Modifié')

        del_post = self.client.post(delete_url)
        self.assertEqual(del_post.status_code, 302)
        self.assertRedirects(del_post, reverse('traffic:point_list'))
        self.assertFalse(MonitoringPoint.objects.filter(pk=new_point.pk).exists())

    def test_snapshot_list_pagination_and_point_filter(self):
        self.client.login(username='citizen_user', password='password123')

        other_point = MonitoringPoint.objects.create(name='Bardo Nord', latitude=36.81, longitude=10.14)
        now = timezone.now()

        # Création de 60 snapshots pour tester la pagination (>50)
        snapshots = [
            TrafficSnapshot(
                point=self.point, timestamp=now - timedelta(minutes=i * 15),
                current_speed=30, free_flow_speed=50, congestion=0.4
            )
            for i in range(55)
        ]
        # Et 2 snapshots pour le second point
        snapshots.append(TrafficSnapshot(point=other_point, timestamp=now, current_speed=40, free_flow_speed=50, congestion=0.2))
        TrafficSnapshot.objects.bulk_create(snapshots)

        # Page 1 : 50 éléments
        res = self.client.get(reverse('traffic:snapshot_list'))
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.context['snapshots']), 50)
        self.assertTrue(res.context['is_paginated'])

        # Page 2 : reste des éléments
        res_page2 = self.client.get(reverse('traffic:snapshot_list') + '?page=2')
        self.assertEqual(res_page2.status_code, 200)
        self.assertGreater(len(res_page2.context['snapshots']), 0)

        # Filtre par point ?point=other_point.id
        res_filter = self.client.get(reverse('traffic:snapshot_list') + f'?point={other_point.id}')
        self.assertEqual(res_filter.status_code, 200)
        for s in res_filter.context['snapshots']:
            self.assertEqual(s.point_id, other_point.id)

    def test_point_create_renders_geolocation_elements(self):
        self.client.login(username='admin_traffic', password='password123')
        response = self.client.get(reverse('traffic:point_create'))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('id="btn-my-location"', content)
        self.assertIn('aria-label="Utiliser ma position actuelle"', content)
        self.assertIn('id="geo-status-message"', content)
        self.assertIn('aria-live="polite"', content)
        self.assertIn('id="btn-recenter-tunis"', content)
        self.assertIn('data-is-create="true"', content)

    def test_point_update_renders_geolocation_elements_and_edit_mode(self):
        self.client.login(username='admin_traffic', password='password123')
        response = self.client.get(reverse('traffic:point_update', kwargs={'pk': self.point.pk}))
        self.assertEqual(response.status_code, 200)
        content = response.content.decode('utf-8')
        self.assertIn('id="btn-my-location"', content)
        self.assertIn('aria-label="Utiliser ma position actuelle"', content)
        self.assertIn('id="geo-status-message"', content)
        self.assertIn('aria-live="polite"', content)
        self.assertIn('id="btn-recenter-tunis"', content)
        self.assertIn('data-is-create="false"', content)
