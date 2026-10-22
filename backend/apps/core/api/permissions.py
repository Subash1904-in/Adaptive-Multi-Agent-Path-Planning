"""API permissions for simulation runs and scenario management.

Provides permission policies that allow open simulation research access
by default while supporting explicit permission hooks and security boundaries.
"""

from django.conf import settings
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.views import APIView


class SimulationApiPermission(BasePermission):
    """Permission class for AMAPP REST API endpoints.

    In development and educational research mode, access is open by default.
    If the Django setting AMAPP_API_REQUIRE_AUTHENTICATION is enabled,
    authenticated credentials are strictly verified.
    If AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS is enabled, write operations
    (POST, PUT, PATCH, DELETE) strictly require staff status.
    """

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check whether the request has permission to access the simulation API."""
        require_auth = getattr(settings, "AMAPP_API_REQUIRE_AUTHENTICATION", False)
        if require_auth and not (request.user and request.user.is_authenticated):
            return False

        require_staff_mutations = getattr(settings, "AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS", False)
        if require_staff_mutations and request.method not in ("GET", "HEAD", "OPTIONS"):
            return bool(request.user and request.user.is_staff)

        return True


class ReadOnlyOrAdminApiPermission(BasePermission):
    """Permission allowing safe read methods for all and write methods only for staff."""

    def has_permission(self, request: Request, view: APIView) -> bool:
        """Allow SAFE_METHODS (GET, HEAD, OPTIONS); restrict POST/PUT/DELETE."""
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        require_auth = getattr(settings, "AMAPP_API_REQUIRE_AUTHENTICATION", False)
        if require_auth:
            return bool(request.user and request.user.is_staff)
        require_staff_mutations = getattr(settings, "AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS", False)
        if require_staff_mutations:
            return bool(request.user and request.user.is_staff)
        return True

