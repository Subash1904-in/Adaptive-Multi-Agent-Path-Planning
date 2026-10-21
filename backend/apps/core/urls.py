"""Core application URL routing."""

from django.urls import include, path

from apps.core.views import HealthCheckView

urlpatterns = [
    path("health/", HealthCheckView.as_view(), name="health_check"),
    path("", include("apps.core.api.urls")),
]
