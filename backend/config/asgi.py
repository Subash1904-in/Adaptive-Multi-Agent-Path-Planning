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
    """Validates WebSocket origin against ALLOWED_HOSTS and AMAPP_WS_ALLOWED_ORIGINS.

    Permits non-browser test communicators and CLI utilities that do not supply an Origin header,
    while strictly evaluating browser Origin headers against configured ALLOWED_HOSTS and explicit
    WebSocket allowed origins.
    """

    def __init__(self, application: Any) -> None:
        self.application = application
        self.inner_validator = AllowedHostsOriginValidator(application)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> Any:
        if scope.get("type") == "websocket":
            headers = dict(scope.get("headers", []))
            origin_bytes = headers.get(b"origin")
            if not origin_bytes:
                return await self.application(scope, receive, send)

            from django.conf import settings

            origin = origin_bytes.decode("latin1", errors="replace").strip()
            allowed_ws = getattr(settings, "AMAPP_WS_ALLOWED_ORIGINS", [])
            if allowed_ws:
                for allowed in allowed_ws:
                    if origin == allowed or origin.rstrip("/") == allowed.rstrip("/"):
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
