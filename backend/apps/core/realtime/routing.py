"""WebSocket URL routing patterns for real-time simulation streaming."""

from django.urls import re_path

from apps.core.realtime.consumer import SimulationRunConsumer

websocket_urlpatterns = [
    re_path(
        r"^ws/v1/runs/(?P<run_id>[a-zA-Z0-9_\-]+)/?$",
        SimulationRunConsumer.as_asgi(),
        name="ws_simulation_run",
    ),
]
