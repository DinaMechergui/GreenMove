"""Accès CRUD et transitions de réservation exigés par la grille."""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from channels.routing import URLRouter
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.urls import re_path

from .models import ChatRoom, Ride, RideBooking
from .consumers import ChatConsumer


class UserScopeMiddleware:
    def __init__(self, app, user):
        self.app = app
        self.user = user

    async def __call__(self, scope, receive, send):
        scope = dict(scope)
        scope['user'] = self.user
        return await self.app(scope, receive, send)


class RideCrudPermissionsTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('ride_owner', 'owner@example.test', 'pass12345!')
        self.other = User.objects.create_user('ride_other', 'other@example.test', 'pass12345!')
        self.ride = Ride.objects.create(
            user=self.owner,
            origin_address='Ariana', origin_lat=36.86, origin_lon=10.19,
            destination_address='Tunis', destination_lat=36.80, destination_lon=10.18,
            departure_datetime=timezone.now() + timedelta(days=1), seats_available=2,
        )
        self.url = reverse('match:api_ride_detail', args=[self.ride.pk])

    def test_owner_can_read_update_and_delete_ride(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        response = self.client.patch(self.url, {'description': 'Mis à jour'}, content_type='application/json')
        self.assertEqual(response.status_code, 200)
        self.ride.refresh_from_db()
        self.assertEqual(self.ride.description, 'Mis à jour')
        self.assertEqual(self.client.delete(self.url).status_code, 204)

    def test_other_user_can_read_but_cannot_mutate(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(
            self.client.patch(self.url, {'description': 'intrusion'}, content_type='application/json').status_code,
            403,
        )
        self.assertEqual(self.client.delete(self.url).status_code, 403)

    def test_booking_requires_owner_decision_and_releases_chat_after_acceptance(self):
        self.client.force_login(self.other)
        response = self.client.post(reverse('match:book_ride', args=[self.ride.pk]), {
            'seats_requested': 1, 'message': 'Bonjour',
        })
        self.assertEqual(response.status_code, 302)
        booking = RideBooking.objects.get(ride=self.ride, passenger=self.other)
        self.assertEqual(booking.status, RideBooking.StatusChoices.PENDING)
        self.client.force_login(self.owner)
        response = self.client.post(reverse('match:manage_booking', args=[booking.pk]), {'action': 'accept'})
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.ride.refresh_from_db()
        self.assertEqual(booking.status, RideBooking.StatusChoices.ACCEPTED)
        self.assertEqual(self.ride.seats_available, 1)

    def test_non_owner_cannot_accept_booking(self):
        booking = RideBooking.objects.create(ride=self.ride, passenger=self.other)
        self.client.force_login(self.other)
        self.client.post(reverse('match:manage_booking', args=[booking.pk]), {'action': 'accept'})
        booking.refresh_from_db()
        self.assertEqual(booking.status, RideBooking.StatusChoices.PENDING)

    def test_chat_is_denied_until_acceptance(self):
        booking = RideBooking.objects.create(ride=self.ride, passenger=self.other)
        self.client.force_login(self.other)
        url = reverse('match:chat_room', args=[self.ride.pk])
        self.assertEqual(self.client.get(url).status_code, 302)
        booking.status = RideBooking.StatusChoices.ACCEPTED
        booking.save(update_fields=['status'])
        room = ChatRoom.objects.create(ride=self.ride)
        room.participants.add(self.owner, self.other)
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_passenger_cancellation_restores_seat(self):
        booking = RideBooking.objects.create(
            ride=self.ride, passenger=self.other, status=RideBooking.StatusChoices.ACCEPTED,
            seats_requested=1,
        )
        self.ride.seats_available = 1
        self.ride.save(update_fields=['seats_available'])
        room = ChatRoom.objects.create(ride=self.ride)
        room.participants.add(self.owner, self.other)
        self.client.force_login(self.other)
        response = self.client.post(reverse('match:manage_booking', args=[booking.pk]), {'action': 'cancel'})
        self.assertEqual(response.status_code, 302)
        booking.refresh_from_db()
        self.ride.refresh_from_db()
        self.assertEqual(booking.status, RideBooking.StatusChoices.CANCELLED)
        self.assertEqual(self.ride.seats_available, 2)
        self.assertFalse(room.participants.filter(pk=self.other.pk).exists())


class ChatWebsocketPermissionTests(TransactionTestCase):
    def setUp(self):
        User = get_user_model()
        self.owner = User.objects.create_user('ws_owner', 'wsowner@example.test', 'pass12345!')
        self.passenger = User.objects.create_user('ws_passenger', 'wspass@example.test', 'pass12345!')
        ride = Ride.objects.create(
            user=self.owner, origin_address='A', origin_lat=36.8, origin_lon=10.1,
            destination_address='B', destination_lat=36.9, destination_lon=10.2,
            departure_datetime=timezone.now() + timedelta(days=1),
        )
        self.room = ChatRoom.objects.create(ride=ride)
        self.room.participants.add(self.owner, self.passenger)
        self.booking = RideBooking.objects.create(ride=ride, passenger=self.passenger)
        self.application = UserScopeMiddleware(URLRouter([
            re_path(r'^ws/match/chat/(?P<room_id>\d+)/$', ChatConsumer.as_asgi()),
        ]), self.passenger)

    async def test_pending_booking_cannot_connect(self):
        communicator = WebsocketCommunicator(self.application, f'/ws/match/chat/{self.room.pk}/')
        connected, close_code = await communicator.connect()
        self.assertFalse(connected)
        self.assertEqual(close_code, 4403)

    async def test_accepted_booking_can_connect_and_receive_history(self):
        await database_sync_to_async(RideBooking.objects.filter(pk=self.booking.pk).update)(
            status=RideBooking.StatusChoices.ACCEPTED
        )
        communicator = WebsocketCommunicator(self.application, f'/ws/match/chat/{self.room.pk}/')
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        payload = await communicator.receive_json_from()
        self.assertEqual(payload['type'], 'chat_history')
        await communicator.disconnect()
