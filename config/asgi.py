"""
Configuration ASGI pour GreenMove avec support Django Channels (WebSockets).
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Initialiser l'application HTTP standard Django
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import match.routing
import rewards.routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                match.routing.websocket_urlpatterns + rewards.routing.websocket_urlpatterns
            )
        )
    ),
})
