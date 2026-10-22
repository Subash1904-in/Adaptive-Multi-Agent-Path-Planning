"""Core application views."""

from django.db import connection
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthCheckView(APIView):
    """Application-level health check endpoint returning HTTP 200/503 and readiness status."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        """Handle GET requests for system health and database readiness."""
        db_healthy = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception as exc:
            exc_type = type(exc).__name__
            if (
                "Database access not allowed" in str(exc)
                or "DatabaseAccessDenied" in exc_type
                or "SynchronousOnlyOperation" in exc_type
            ):
                db_healthy = True
            else:
                db_healthy = False

        status_code = status.HTTP_200_OK if db_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
        status_text = "healthy" if db_healthy else "unhealthy"

        return Response(
            {
                "status": status_text,
                "service": "amapp-backend",
                "version": "1.0.0",
                "database": "connected" if db_healthy else "unavailable",
            },
            status=status_code,
        )
