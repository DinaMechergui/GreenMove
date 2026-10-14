"""
Notifications Telegram Bot (MobilityMatch) — gratuit, sans serveur.
Configuration dans .env :
    TELEGRAM_BOT_TOKEN=  (créé via @BotFather)
    TELEGRAM_CHAT_ID=    (chat par défaut, ex: id d'un groupe ou d'un canal)

Le module est un no-op propre tant que le token n'est pas renseigné.
"""
import logging
from typing import Optional

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API_TIMEOUT = 5.0


def telegram_enabled() -> bool:
    """True si un token est configuré."""
    return bool(getattr(settings, 'TELEGRAM_BOT_TOKEN', ''))


def send_telegram(text: str, chat_id: Optional[str] = None) -> bool:
    """
    Envoie un message Telegram. Retourne False en cas d'échec ou si non configuré.
    N'élève jamais d'exception.
    """
    token = getattr(settings, 'TELEGRAM_BOT_TOKEN', '')
    if not token:
        logger.debug("Telegram non configuré — message ignoré : %s", text[:80])
        return False

    target = chat_id or getattr(settings, 'TELEGRAM_CHAT_ID', '')
    if not target:
        logger.warning("TELEGRAM_CHAT_ID manquant — message non envoyé.")
        return False

    try:
        res = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={'chat_id': target, 'text': text, 'parse_mode': 'HTML'},
            timeout=TELEGRAM_API_TIMEOUT,
        )
        if res.status_code == 200 and res.json().get('ok'):
            return True
        logger.warning("Telegram API erreur HTTP %s : %s", res.status_code, res.text[:200])
    except Exception as exc:
        logger.warning("Échec d'envoi Telegram : %s", exc)
    return False


# -----------------------------------------
# Notifications métier
# -----------------------------------------

def notify_booking(booking) -> bool:
    """Nouvelle réservation sur un trajet."""
    ride = booking.ride
    return send_telegram(
        f"🟢 <b>GreenMove — Nouvelle réservation</b>\n"
        f"Trajet : {ride.origin_address} → {ride.destination_address}\n"
        f"Passager : {booking.passenger.get_full_name() or booking.passenger.username}\n"
        f"Places : {booking.seats_requested}\n"
        f"Départ : {ride.departure_datetime.strftime('%d/%m %Y à %H:%M')}"
    )


def notify_match(user, match_pct: int, origin: str, destination: str) -> bool:
    """Nouveau match de trajectoire trouvé pour un utilisateur."""
    return send_telegram(
        f"💜 <b>GreenMove — Nouveau match à {match_pct}%</b>\n"
        f"{origin} → {destination}\n"
        f"Connectez-vous pour réserver votre place."
    )


def notify_sos(alert) -> bool:
    """Alerte de sécurité SOS."""
    ride = alert.ride
    position = (
        f"\nPosition : https://www.google.com/maps?q={alert.latitude},{alert.longitude}"
        if alert.latitude and alert.longitude else ""
    )
    trajet = (
        f"\nTrajet : {ride.origin_address} → {ride.destination_address}"
        if ride else ""
    )
    return send_telegram(
        f"🆘 <b>GreenMove — ALERTE SOS</b>\n"
        f"Utilisateur : {alert.user.get_full_name() or alert.user.username}"
        f"{trajet}{position}\n"
        f"Heure : {alert.created_at.strftime('%d/%m/%Y à %H:%M')}"
    )


def notify_trip_reminder(ride, hours_before: int = 1) -> bool:
    """Rappel de départ pour un trajet récurrent."""
    return send_telegram(
        f"⏰ <b>GreenMove — Rappel de trajet</b>\n"
        f"Dans ~{hours_before}h : {ride.origin_address} → {ride.destination_address}\n"
        f"Départ : {ride.departure_datetime.strftime('%d/%m à %H:%M')}"
    )
