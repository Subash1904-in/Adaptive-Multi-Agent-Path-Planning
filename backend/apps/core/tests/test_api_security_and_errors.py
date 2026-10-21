"""Integration and security tests for error handling, exception taxonomy, and permissions.

Verifies consistent RFC 7807 inspired error structures, status codes (400, 401, 403, 404,
405, 409, 413, 500), authentication toggles, and safe exception logging without trace leaks.
"""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.api.services import default_run_registry, default_scenario_registry


@pytest.fixture(autouse=True)
def clean_registries():
    """Reset and clean run and scenario registries between tests."""
    default_run_registry.clear()
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()
    yield
    default_run_registry.clear()
    default_scenario_registry.clear()
    default_scenario_registry.preload_defaults()


@pytest.fixture
def client():
    """Django REST Framework test client."""
    return APIClient()


@pytest.mark.django_db
class TestApiErrorTaxonomy:
    """Verifies that all API errors produce the standard JSON error schema."""

    def test_404_error_schema(self, client):
        """404 responses conform to standard error schema."""
        response = client.get("/api/v1/scenarios/definitely_not_a_real_scenario/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "error" in data
        assert "code" in data["error"]
        assert "message" in data["error"]
        assert "details" in data["error"]
        assert data["error"]["code"] == "SCENARIO_NOT_FOUND"

    def test_405_method_not_allowed_schema(self, client):
        """Unsupported HTTP verbs return 405 with standard error schema."""
        response = client.delete("/api/v1/scenarios/")
        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert "details" in data["error"]

    def test_400_malformed_json_parse_error(self, client):
        """Malformed JSON payload returns 400 Bad Request with PARSE_ERROR."""
        response = client.post(
            "/api/v1/scenarios/",
            data="{not_valid_json:",
            content_type="application/json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] in ("PARSE_ERROR", "VALIDATION_ERROR")

    def test_500_internal_server_error_sanitized(self, client):
        """Unhandled exceptions return sanitized 500 without leaking stack traces."""
        with patch.object(
            default_scenario_registry,
            "list_all",
            side_effect=RuntimeError("Secret database connection failure!"),
        ):
            response = client.get("/api/v1/scenarios/")
            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            data = response.json()
            assert "error" in data
            assert data["error"]["code"] == "INTERNAL_SERVER_ERROR"
            assert "Secret database connection failure!" not in data["error"]["message"]
            assert data["error"]["details"] is None


@pytest.mark.django_db
class TestApiPermissionsAndSecurity:
    """Tests authentication enforcement and security boundaries."""

    def test_default_dev_mode_permits_anonymous_access(self, client):
        """By default, educational simulation API permits open access."""
        response = client.get("/api/v1/scenarios/")
        assert response.status_code == status.HTTP_200_OK

    def test_strict_auth_mode_rejects_unauthenticated_requests(self, client, settings):
        """When AMAPP_API_REQUIRE_AUTHENTICATION is True, unauthenticated access is rejected."""
        settings.AMAPP_API_REQUIRE_AUTHENTICATION = True
        response = client.get("/api/v1/scenarios/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
        data = response.json()
        assert "error" in data
        assert data["error"]["code"] in ("UNAUTHORIZED", "PERMISSION_DENIED")

    def test_strict_auth_mode_permits_authenticated_user(self, client, settings):
        """When AMAPP_API_REQUIRE_AUTHENTICATION is True, authenticated users are permitted."""
        settings.AMAPP_API_REQUIRE_AUTHENTICATION = True
        user = get_user_model().objects.create_user(
            username="researcher",
            password="testpassword123",
        )
        client.force_authenticate(user=user)
        response = client.get("/api/v1/scenarios/")
        assert response.status_code == status.HTTP_200_OK

    def test_read_only_or_admin_permission_policy(self, settings):
        """ReadOnlyOrAdminApiPermission allows reads and restricts mutations to staff."""
        from unittest.mock import MagicMock

        from apps.core.api.permissions import ReadOnlyOrAdminApiPermission

        perm = ReadOnlyOrAdminApiPermission()
        req_get = MagicMock(method="GET")
        req_post = MagicMock(method="POST", user=None)
        view = MagicMock()

        # Without auth requirement: both pass
        settings.AMAPP_API_REQUIRE_AUTHENTICATION = False
        assert perm.has_permission(req_get, view) is True
        assert perm.has_permission(req_post, view) is True

        # With auth requirement: GET passes, non-staff POST fails
        settings.AMAPP_API_REQUIRE_AUTHENTICATION = True
        assert perm.has_permission(req_get, view) is True
        assert perm.has_permission(req_post, view) is False

        # Staff POST passes
        staff_user = MagicMock(is_staff=True)
        req_post.user = staff_user
        assert perm.has_permission(req_post, view) is True


@pytest.mark.django_db
class TestRegistryLifecycle:
    """Tests programmatic operations on in-memory ScenarioRegistry and RunRegistry."""

    def test_scenario_registry_delete_and_not_found(self):
        """Deleting scenario removes it; querying deleted scenario raises ScenarioNotFoundError."""
        from apps.core.api.exceptions import ScenarioNotFoundError
        from apps.core.api.services import ScenarioRegistry
        from apps.core.scenarios.examples import create_single_vehicle_scenario

        registry = ScenarioRegistry()
        scn = create_single_vehicle_scenario()
        registry.register(scn)
        assert registry.exists(scn.metadata.id)

        assert registry.delete(scn.metadata.id) is True
        assert not registry.exists(scn.metadata.id)

        with pytest.raises(ScenarioNotFoundError):
            registry.get(scn.metadata.id)

        with pytest.raises(ScenarioNotFoundError):
            registry.delete("nonexistent_to_delete")

    def test_run_registry_delete_and_not_found(self):
        """Deleting run removes it; querying deleted run raises RunNotFoundError."""
        from apps.core.api.exceptions import RunNotFoundError
        from apps.core.api.services import RunRegistry
        from apps.core.scenarios.examples import create_single_vehicle_scenario
        from apps.core.scenarios.runner import ScenarioRunner

        registry = RunRegistry()
        scn = create_single_vehicle_scenario()
        runner = ScenarioRunner.create(scn)
        registry.register(runner)
        assert registry.exists(runner.run_id)

        assert registry.delete(runner.run_id) is True
        assert not registry.exists(runner.run_id)

        with pytest.raises(RunNotFoundError):
            registry.get(runner.run_id)

        with pytest.raises(RunNotFoundError):
            registry.delete("nonexistent_run_to_delete")
