"""Automated tests for health check endpoint."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    """Fixture providing an unauthenticated REST framework API test client."""
    return APIClient()


@pytest.mark.django_db
def test_health_check_returns_http_200(api_client):
    """Verify GET /api/v1/health/ returns HTTP 200 OK."""
    url = reverse("health_check")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK


def test_health_check_content_type(api_client):
    """Verify health check response Content-Type is application/json."""
    url = reverse("health_check")
    response = api_client.get(url)
    assert response["Content-Type"].startswith("application/json")


def test_health_check_payload_schema(api_client):
    """Verify health check JSON payload matches documented schema."""
    url = reverse("health_check")
    response = api_client.get(url)
    data = response.json()

    assert isinstance(data, dict)
    assert data.get("status") == "healthy"
    assert data.get("service") == "amapp-backend"
    assert data.get("version") == "1.0.0"


def test_health_check_unauthenticated_access(api_client):
    """Verify health check endpoint requires no credentials or authentication tokens."""
    url = reverse("health_check")
    # Explicitly ensure no auth headers are attached
    api_client.credentials()
    response = api_client.get(url)
    assert response.status_code == status.HTTP_200_OK


def test_invalid_path_returns_http_404(api_client):
    """Verify requesting an invalid/unregistered endpoint returns HTTP 404 Not Found."""
    response = api_client.get("/api/v1/unregistered-path/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
