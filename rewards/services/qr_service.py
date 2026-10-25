"""
Service de génération de QR Codes sécurisés et codes coupons
pour les récompenses partenaires GreenMove.
"""
import io
import base64
import uuid
import json
from typing import Optional
import qrcode


def generate_unique_coupon_code() -> str:
    """Génère un code coupon unique et lisible en caisse (ex: GM-ECO-A7F92B)."""
    random_part = uuid.uuid4().hex[:6].upper()
    return f"GM-ECO-{random_part}"


def generate_coupon_qr_base64(
    coupon_code: str,
    reward_title: str,
    user_identifier: str,
    verification_url: Optional[str] = None
) -> str:
    """
    Génère un QR Code sous forme de Data URI Base64 PNG.
    Le QR Code contient les métadonnées vérifiables par les commerçants partenaires.
    """
    payload = {
        'app': 'GreenMove-EcoRewards',
        'coupon': coupon_code,
        'title': reward_title,
        'user': user_identifier,
        'verify': verification_url or f"https://greenmove.tn/rewards/verify/{coupon_code}/"
    }

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=3,
    )
    qr.add_data(json.dumps(payload, separators=(',', ':')))
    qr.make(fit=True)

    img = qr.make_image(fill_color="#264634", back_color="#FFFFFF")
    
    buffer = io.BytesIO()
    img.save(buffer)
    b64_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return f"data:image/png;base64,{b64_str}"
