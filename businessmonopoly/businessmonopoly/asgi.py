import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from whitenoise import WhiteNoise
import games.routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'businessmonopoly.settings')

django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            games.routing.websocket_urlpatterns
        )
    ),
})
