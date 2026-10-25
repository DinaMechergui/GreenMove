"""
Consommateurs WebSocket pour l'application EcoRewards & Gamification.
Permet la diffusion en temps réel du classement (global, par quartier, par établissement)
et des notifications de gains de points ou déblocage de badges.
"""
import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


class LeaderboardConsumer(AsyncWebsocketConsumer):
    """
    Diffuse en temps réel les mises à jour du classement éco-responsable.
    """
    async def connect(self):
        self.group_name = 'rewards_leaderboard'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Envoyer l'état initial du classement à la connexion
        leaderboard_data = await self.get_top_leaderboard()
        await self.send(text_data=json.dumps({
            'type': 'initial_leaderboard',
            'data': leaderboard_data
        }))

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
            action = payload.get('action')
            if action == 'get_rankings':
                category = payload.get('category', 'global')
                val = payload.get('value', '')
                data = await self.get_top_leaderboard(category=category, filter_val=val)
                await self.send(text_data=json.dumps({
                    'type': 'filtered_leaderboard',
                    'category': category,
                    'data': data
                }))
        except Exception:
            pass

    async def leaderboard_updated(self, event):
        """Reçoit une alerte de mise à jour globale et renvoie le nouveau classement."""
        leaderboard_data = await self.get_top_leaderboard()
        await self.send(text_data=json.dumps({
            'type': 'leaderboard_updated',
            'message': event.get('message', 'Classement mis à jour !'),
            'data': leaderboard_data
        }))

    @database_sync_to_async
    def get_top_leaderboard(self, category: str = 'global', filter_val: str = ''):
        from accounts.models import CustomUser
        from rewards.models import UserGamificationProfile

        qs = CustomUser.objects.filter(is_active=True).select_related('gamification_profile')

        if category == 'district' and filter_val:
            qs = qs.filter(gamification_profile__district__icontains=filter_val)
        elif category == 'organization' and filter_val:
            qs = qs.filter(gamification_profile__organization__icontains=filter_val)

        users = qs.order_by('-eco_points')[:10]
        results = []
        for rank, u in enumerate(users, start=1):
            prof = getattr(u, 'gamification_profile', None)
            co2 = prof.total_co2_saved_kg if prof else 0.0
            dist = prof.district if prof else 'Grand Tunis'
            org = prof.organization if prof else 'ESPRIT'
            lvl = prof.current_level_name if prof else 'Graine Verte'
            results.append({
                'rank': rank,
                'username': u.get_full_name() or u.username,
                'avatar': u.avatar.url if u.avatar else None,
                'eco_points': u.eco_points,
                'co2_saved_kg': round(co2, 1),
                'district': dist,
                'organization': org,
                'level_name': lvl,
            })
        return results
