"""Core application views."""
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Application-level health check endpoint returning HTTP 200 and basic service status."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        """Handle GET requests for system health."""
        return Response(
            {
                "status": "healthy",
                "service": "amapp-backend",
                "version": "1.0.0",
            },
            status=status.HTTP_200_OK,
        )
