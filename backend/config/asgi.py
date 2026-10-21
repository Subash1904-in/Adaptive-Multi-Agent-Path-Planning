"""ASGI config for AMAPP project.

It exposes the ASGI callable as a module-level variable named ``application``.
Routes HTTP traffic to standard Django ASGI and WebSocket traffic to Channels URLRouter.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# Initialize Django ASGI application early to ensure the AppRegistry
# is populated before importing code that may import ORM models or settings.
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

from apps.core.realtime.routing import websocket_urlpatterns  # noqa: E402


class SimulationOriginValidator:
    """Validates WebSocket origin against ALLOWED_HOSTS when present.

    Permits non-browser test communicators and CLI utilities that do not supply an Origin header,
    while strictly evaluating browser Origin headers against configured ALLOWED_HOSTS.
    """

    def __init__(self, application: Any) -> None:
        self.application = application
        self.inner_validator = AllowedHostsOriginValidator(application)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        if scope.get("type") == "websocket":
            has_origin = any(h[0] == b"origin" for h in scope.get("headers", []))
            if not has_origin:
                return await self.application(scope, receive, send)
            return await self.inner_validator(scope, receive, send)
        return await self.application(scope, receive, send)


application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": SimulationOriginValidator(
            AuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
