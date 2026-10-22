"""Tests for API input sanitization, finite numeric validation, role-based mutation, and throttling.

Validates:
- Path parameter sanitization (rejecting traversal, null bytes, special characters).
- Numerical validation (rejection of NaN, +Inf, -Inf in acceleration, metrics, incidents).
- Role-based mutation access control under AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS.
- Throttled exception translation into RFC 7807 format with code RATE_LIMIT_EXCEEDED.
- HTTP method enforcement (405 on unsupported methods).
"""

from __future__ import annotations

from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework import status
from rest_framework.exceptions import Throttled
from rest_framework.test import APITestCase

from apps.core.api.exceptions import api_exception_handler
from apps.core.api.serializers import (
    CreateIncidentRequestSerializer,
    MetricsQuerySerializer,
    RunCreateRequestSerializer,
    RunStepRequestSerializer,
)
from apps.core.api.services import default_run_registry, default_scenario_registry

User = get_user_model()


class ApiValidationAndSanitizationTestCase(APITestCase):
    """Verifies strict input sanitization and finite numeric enforcement."""

    def setUp(self) -> None:
        super().setUp()
        default_run_registry.clear()
        default_scenario_registry.clear()
        default_scenario_registry.preload_defaults()

    def test_run_id_validation_rejects_path_traversal_and_malformed_chars(self) -> None:
        """Reject run_ids with path traversal, null bytes, slashes, or invalid characters."""
        invalid_ids = [
            "../escaped_id",
            "run/with/slash",
            "run\\backslash",
            "run\x00nullbyte",
            "run$illegal",
            "run;drop_table",
            " ",
            "a" * 129,
        ]
        for bad_id in invalid_ids:
            serializer = RunCreateRequestSerializer(
                data={"scenario_id": "scn_single_veh", "run_id": bad_id}
            )
            self.assertFalse(
                serializer.is_valid(),
                f"Expected serializer to reject invalid run_id: '{bad_id}'",
            )
            self.assertIn("run_id", serializer.errors)

    def test_path_parameter_sanitization_in_views(self) -> None:
        """URL path parameters with traversal or illegal characters are rejected with HTTP 400."""
        # Traversal sequence in scenario_id
        resp = self.client.get("/api/v1/scenarios/..traversal/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")

        # Illegal symbol in run_id
        resp = self.client.get("/api/v1/runs/bad$run_id/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")

        # Traversal in incident_id
        resp = self.client.get("/api/v1/runs/valid_run_id/incidents/..incident/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.json()["error"]["code"], "VALIDATION_ERROR")

    def test_target_accels_finite_numeric_and_bounds_validation(self) -> None:
        """Target accelerations must be finite numbers within physical bounds (+/- 50 m/s^2)."""
        # Rejection of NaN
        s_nan = RunStepRequestSerializer(
            data={"ticks": 1, "target_accels": {"veh_01": float("nan")}}
        )
        self.assertFalse(s_nan.is_valid())
        self.assertIn("target_accels", s_nan.errors)

        # Rejection of +Inf and -Inf
        s_inf = RunStepRequestSerializer(
            data={"ticks": 1, "target_accels": {"veh_01": float("inf")}}
        )
        self.assertFalse(s_inf.is_valid())
        self.assertIn("target_accels", s_inf.errors)

        s_ninf = RunStepRequestSerializer(
            data={"ticks": 1, "target_accels": {"veh_01": float("-inf")}}
        )
        self.assertFalse(s_ninf.is_valid())
        self.assertIn("target_accels", s_ninf.errors)

        # Rejection of physically impossible values (> 50 m/s^2)
        s_oob = RunStepRequestSerializer(data={"ticks": 1, "target_accels": {"veh_01": 999.0}})
        self.assertFalse(s_oob.is_valid())
        self.assertIn("target_accels", s_oob.errors)

        # Rejection of non-string keys
        s_badkey = RunStepRequestSerializer(data={"ticks": 1, "target_accels": {"": 2.5}})
        self.assertFalse(s_badkey.is_valid())
        self.assertIn("target_accels", s_badkey.errors)

        # Acceptance of valid finite accelerations
        s_valid = RunStepRequestSerializer(data={"ticks": 1, "target_accels": {"veh_01": -3.5}})
        self.assertTrue(s_valid.is_valid())
        self.assertEqual(s_valid.validated_data["target_accels"]["veh_01"], -3.5)

    def test_metrics_query_finite_window_validation(self) -> None:
        """MetricsQuerySerializer rejects non-finite time window parameters."""
        s_nan = MetricsQuerySerializer(data={"time_window_start_s": float("nan")})
        self.assertFalse(s_nan.is_valid())
        self.assertIn("time_window_start_s", s_nan.errors)

        s_inf = MetricsQuerySerializer(data={"time_window_end_s": float("inf")})
        self.assertFalse(s_inf.is_valid())
        self.assertIn("time_window_end_s", s_inf.errors)

    def test_incident_serializer_finite_parameters_validation(self) -> None:
        """CreateIncidentRequestSerializer rejects non-finite congestion and duration values."""
        s_nan_cong = CreateIncidentRequestSerializer(
            data={"incident_type": "congestion", "congestion_factor": float("nan")}
        )
        self.assertFalse(s_nan_cong.is_valid())
        self.assertIn("congestion_factor", s_nan_cong.errors)

        s_inf_dur = CreateIncidentRequestSerializer(
            data={"incident_type": "road_closure", "duration_s": float("inf")}
        )
        self.assertFalse(s_inf_dur.is_valid())
        self.assertIn("duration_s", s_inf_dur.errors)

        s_oob_cong = CreateIncidentRequestSerializer(
            data={"incident_type": "congestion", "congestion_factor": 50000.0}
        )
        self.assertFalse(s_oob_cong.is_valid())
        self.assertIn("congestion_factor", s_oob_cong.errors)


class RoleBasedMutationTestCase(APITestCase):
    """Verifies that mutating operations require staff status when configured."""

    def setUp(self) -> None:
        super().setUp()
        default_run_registry.clear()
        default_scenario_registry.clear()
        default_scenario_registry.preload_defaults()

        # Create standard user and staff user
        self.user = User.objects.create_user(username="researcher", password="password123")
        self.staff_user = User.objects.create_user(
            username="admin_researcher", password="password123", is_staff=True
        )

    @override_settings(AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS=True)
    def test_non_staff_cannot_create_or_mutate_simulation(self) -> None:
        """Standard authenticated non-staff user receives 403 FORBIDDEN on POST."""
        self.client.force_authenticate(user=self.user)

        # GET is permitted
        resp_get = self.client.get("/api/v1/scenarios/")
        self.assertEqual(resp_get.status_code, status.HTTP_200_OK)

        # POST is forbidden
        resp_post = self.client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "forbidden_run"},
            format="json",
        )
        self.assertEqual(resp_post.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp_post.json()["error"]["code"], "PERMISSION_DENIED")

    @override_settings(AMAPP_API_REQUIRE_STAFF_FOR_MUTATIONS=True)
    def test_staff_user_can_create_and_mutate_simulation(self) -> None:
        """Staff user can successfully create and advance simulation runs."""
        self.client.force_authenticate(user=self.staff_user)

        resp_create = self.client.post(
            "/api/v1/runs/",
            data={"scenario_id": "scn_single_veh", "run_id": "staff_run_01"},
            format="json",
        )
        self.assertEqual(resp_create.status_code, status.HTTP_201_CREATED)

        # Step simulation run
        resp_step = self.client.post(
            "/api/v1/runs/staff_run_01/step/",
            data={"ticks": 1},
            format="json",
        )
        self.assertEqual(resp_step.status_code, status.HTTP_200_OK)


class ThrottlingAndMethodNotAllowedTestCase(APITestCase):
    """Verifies DRF throttling exception translation and HTTP method enforcement."""

    def test_throttled_exception_formatting(self) -> None:
        """DRF Throttled exception translates to RFC 7807 with code RATE_LIMIT_EXCEEDED."""
        exc = Throttled(wait=42)
        resp = api_exception_handler(exc, {"view": MagicMock(), "request": MagicMock()})
        self.assertIsNotNone(resp)
        self.assertEqual(resp.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        data = resp.data
        self.assertEqual(data["error"]["code"], "RATE_LIMIT_EXCEEDED")
        self.assertEqual(data["error"]["details"]["available_in_seconds"], 42)

    def test_method_not_allowed_on_readonly_views(self) -> None:
        """Unsupported HTTP method returns 405 METHOD_NOT_ALLOWED."""
        resp = self.client.put("/api/v1/scenarios/", data={})
        self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(resp.json()["error"]["code"], "METHOD_NOT_ALLOWED")
