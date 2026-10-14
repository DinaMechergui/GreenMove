"""
Consommateurs WebSocket : notifications de matching, chat temps réel,
suivi live géolocalisé et diffusion des alertes SOS.
"""
import json
from datetime import timedelta

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.utils import timezone


class MatchNotificationConsumer(AsyncWebsocketConsumer):
    """
    Consommateur pour les notifications personnelles de matching et réservations.
    Sécurisé : un utilisateur ne peut écouter que son propre groupe.
    """
    async def connect(self):
        self.user_id = self.scope['url_route']['kwargs']['user_id']
        user = self.scope.get('user')
        if user is None or user.is_anonymous or str(user.pk) != str(self.user_id):
            await self.close(code=4403)
            return

        self.room_group_name = f'user_notifications_{self.user_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        await self.send(text_data=json.dumps({
            'status': 'received',
            'echo': data
        }))

    async def match_notification(self, event):
        """Reçoit un message du groupe et l'envoie au WebSocket du client."""
        await self.send(text_data=json.dumps(event['message']))


class RideUpdatesConsumer(AsyncWebsocketConsumer):
    """
    Consommateur pour les mises à jour publiques sur les nouveaux trajets.
    """
    async def connect(self):
        self.room_group_name = 'public_ride_updates'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def ride_broadcast(self, event):
        await self.send(text_data=json.dumps(event['message']))


@database_sync_to_async
def _load_room(room_id, user):
    from .models import ChatRoom, ChatMessage
    try:
        room = ChatRoom.objects.select_related('ride').get(pk=room_id)
    except ChatRoom.DoesNotExist:
        return None, []
    if user is None or user.is_anonymous or not room.participants.filter(pk=user.pk).exists():
        return None, []
    messages = [
        {
            'id': m.id,
            'sender': m.sender_id,
            'sender_name': (m.sender.get_full_name() or m.sender.username) if m.sender else 'GreenMove',
            'content': m.content,
            'created_at': m.created_at.strftime('%H:%M'),
        }
        for m in room.messages.select_related('sender').order_by('created_at')[:100]
        if not m.is_suggestion
    ]
    suggestions = list(
        room.messages.filter(is_suggestion=True, sender=None)
        .order_by('created_at').values_list('content', flat=True)
    )
    return room, {'messages': messages, 'suggestions': suggestions}


@database_sync_to_async
def _save_message(room_id, user_id, content):
    from .models import ChatMessage, ChatRoom
    from accounts.models import CustomUser
    try:
        room = ChatRoom.objects.get(pk=room_id)
        sender = CustomUser.objects.get(pk=user_id)
    except Exception:
        return None
    msg = ChatMessage.objects.create(room=room, sender=sender, content=content[:2000])
    return {
        'id': msg.id,
        'sender': sender.pk,
        'sender_name': sender.get_full_name() or sender.username,
        'content': msg.content,
        'created_at': msg.created_at.strftime('%H:%M'),
    }


class ChatConsumer(AsyncWebsocketConsumer):
    """
    Chat temps réel d'un trajet (room par trajet).
    Diffuse les messages entrants à tous les participants du salon.
    """
    async def connect(self):
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        user = self.scope.get('user')
        room, payload = await _load_room(self.room_id, user)
        if room is None:
            await self.close(code=4403)
            return

        self.room_group_name = f'chat_room_{self.room_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'chat_history',
            'messages': payload['messages'],
            'suggestions': payload['suggestions'],
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            content = (data.get('content') or '').strip()
        except (ValueError, TypeError):
            return
        if not content:
            return
        user = self.scope.get('user')
        if user is None or user.is_anonymous:
            return
        payload = await _save_message(self.room_id, user.pk, content[:2000])
        if payload:
            await self.channel_layer.group_send(
                self.room_group_name,
                {'type': 'chat_message', 'message': payload}
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({'type': 'chat_message', 'message': event['message']}))


@database_sync_to_async
def _validate_tracking(token, user):
    from .models import TrackingLink
    try:
        link = TrackingLink.objects.select_related('ride', 'owner').get(token=token)
    except TrackingLink.DoesNotExist:
        return None
    if not link.is_valid:
        return None
    is_owner = bool(user and not user.is_anonymous and user.pk == link.owner_id)
    return {'is_owner': is_owner, 'ride_id': link.ride_id}


@database_sync_to_async
def _store_position(token, lat, lon):
    from .models import TrackingLink
    from django.core.cache import cache
    cache.set(f"live_pos_{token}", {
        'lat': lat,
        'lon': lon,
        'ts': timezone.now().isoformat(),
    }, 300)


class TrackingConsumer(AsyncWebsocketConsumer):
    """
    Suivi live d'un trajet via lien partagé (token UUID).
    Seul le propriétaire diffuse sa position ; les invités suivent en lecture.
    """
    async def connect(self):
        self.token = self.scope['url_route']['kwargs']['token']
        user = self.scope.get('user')
        info = await _validate_tracking(self.token, user)
        if info is None:
            await self.close(code=4403)
            return
        self.is_owner = info['is_owner']
        self.room_group_name = f'tracking_{self.token}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'tracking_role',
            'role': 'broadcaster' if self.is_owner else 'viewer',
        }))

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        if not getattr(self, 'is_owner', False):
            await self.send(text_data=json.dumps({'type': 'error', 'message': 'Lecture seule'}))
            return
        try:
            data = json.loads(text_data)
            lat = float(data['lat'])
            lon = float(data['lon'])
        except (ValueError, TypeError, KeyError):
            return
        await _store_position(self.token, lat, lon)
        await self.channel_layer.group_send(
            self.room_group_name,
            {'type': 'tracking_update', 'lat': lat, 'lon': lon}
        )

    async def tracking_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'tracking_update',
            'lat': event['lat'],
            'lon': event['lon'],
            'ts': timezone.now().strftime('%H:%M:%S'),
        }))


class SOSConsumer(AsyncWebsocketConsumer):
    """
    Diffusion des alertes SOS aux participants d'un trajet.
    """
    async def connect(self):
        user = self.scope.get('user')
        if user is None or user.is_anonymous:
            await self.close(code=4403)
            return
        self.ride_id = self.scope['url_route']['kwargs']['ride_id']
        self.room_group_name = f'sos_alerts_{self.ride_id}'
        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def sos_alert(self, event):
        await self.send(text_data=json.dumps(event['message']))
