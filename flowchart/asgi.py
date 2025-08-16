# flowchart/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from channels.auth import AuthMiddlewareStack
from community.consumers import ProjectChatConsumer
from community.ws_auth import JwtQueryAuthMiddleware  # (see #2)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "flowchart.settings")
django_asgi_app = get_asgi_application()

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": JwtQueryAuthMiddleware(   # JWT-aware; falls back to session auth
        AuthMiddlewareStack(
            URLRouter([
                path("ws/chat/project/<int:project_id>/", ProjectChatConsumer.as_asgi()),
            ])
        )
    ),
})
