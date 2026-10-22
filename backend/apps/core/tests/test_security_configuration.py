"""Tests for Django security configuration, secret key validation, and defense in depth.

Validates:
- Strict secret key enforcement when DEBUG is False (rejects empty, weak, placeholder, short keys).
- Allowed hosts validation when DEBUG is False (rejects empty or wildcard '*').
- Security response headers and cookie security flags.
- Request payload and file upload size boundaries.
- Safe logging and exception masking (HTTP 500 without leaking stack traces or internal secrets).
"""

from __future__ import annotations

import logging
import os
import unittest
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.api.exceptions import api_exception_handler


class SettingsSecurityValidationTestCase(SimpleTestCase):
    """Verifies environment-driven configuration checks and safe production constraints."""

    def test_secret_key_rejection_in_production_mode(self) -> None:
        """When DEBUG is False, weak, short, or placeholder keys must raise ValueError."""
        # Test missing secret key
        with patch.dict(os.environ, {"DEBUG": "False", "DJANGO_SECRET_KEY": ""}, clear=True):
            with self.assertRaises(ValueError) as ctx:
                import importlib

                import config.settings

                importlib.reload(config.settings)
            self.assertIn("strictly required", str(ctx.exception))

        # Test placeholder key
        with patch.dict(
            os.environ,
            {
                "DEBUG": "False",
                "DJANGO_SECRET_KEY": (
                    "django-insecure-dev-fallback-key-for-local-testing-only-amapp"
                ),
            },
            clear=True,
        ):
            with self.assertRaises(ValueError) as ctx:
                import importlib

                import config.settings

                importlib.reload(config.settings)
            self.assertIn("must be a secure, non-placeholder key", str(ctx.exception))

        # Test short key (< 32 chars)
        with patch.dict(
            os.environ,
            {"DEBUG": "False", "DJANGO_SECRET_KEY": "short-secret-key-too-short"},
            clear=True,
        ):
            with self.assertRaises(ValueError) as ctx:
                import importlib

                import config.settings

                importlib.reload(config.settings)
            self.assertIn("at least 32 characters", str(ctx.exception))

        # Reload with normal test settings to restore state
        with patch.dict(os.environ, {"DEBUG": "True", "DJANGO_SECRET_KEY": ""}, clear=True):
            import importlib

            import config.settings

            importlib.reload(config.settings)

    def test_allowed_hosts_rejection_in_production_mode(self) -> None:
        """When DEBUG is False, empty or wildcard ALLOWED_HOSTS must raise ValueError."""
        with patch.dict(
            os.environ,
            {
                "DEBUG": "False",
                "DJANGO_SECRET_KEY": "a" * 40,
                "ALLOWED_HOSTS": "*",
            },
            clear=True,
        ):
            with self.assertRaises(ValueError) as ctx:
                import importlib

                import config.settings

                importlib.reload(config.settings)
            self.assertIn("ALLOWED_HOSTS must not be empty or wildcard", str(ctx.exception))

        # Reload with normal test settings to restore state
        with patch.dict(os.environ, {"DEBUG": "True", "DJANGO_SECRET_KEY": ""}, clear=True):
            import importlib

            import config.settings

            importlib.reload(config.settings)

    def test_security_headers_and_cookie_attributes_configured(self) -> None:
        """Verify baseline security headers and cookie security flags."""
        self.assertTrue(getattr(settings, "SECURE_CONTENT_TYPE_NOSNIFF", False))
        self.assertEqual(getattr(settings, "X_FRAME_OPTIONS", None), "DENY")
        self.assertTrue(getattr(settings, "SESSION_COOKIE_HTTPONLY", False))
        self.assertTrue(getattr(settings, "CSRF_COOKIE_HTTPONLY", False))

    def test_upload_and_request_memory_limits_configured(self) -> None:
        """Verify bound limits against denial of service via oversized uploads."""
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 10 * 1024 * 1024)
        self.assertLessEqual(settings.FILE_UPLOAD_MAX_MEMORY_SIZE, 10 * 1024 * 1024)
        self.assertLessEqual(settings.DATA_UPLOAD_MAX_NUMBER_FIELDS, 1000)

    def test_throttling_classes_and_rates_configured(self) -> None:
        """Verify DRF throttling classes and standard rates are defined."""
        rf = settings.REST_FRAMEWORK
        throttle_classes = rf.get("DEFAULT_THROTTLE_CLASSES", [])
        self.assertTrue(any("AnonRateThrottle" in cls for cls in throttle_classes))
        self.assertTrue(any("UserRateThrottle" in cls for cls in throttle_classes))
        self.assertTrue(any("ScopedRateThrottle" in cls for cls in throttle_classes))

        rates = rf.get("DEFAULT_THROTTLE_RATES", {})
        self.assertIn("anon", rates)
        self.assertIn("user", rates)
        self.assertIn("simulation_step", rates)
        self.assertIn("simulation_create", rates)


class ExceptionHandlerSecurityTestCase(SimpleTestCase):
    """Verifies that unexpected exceptions return sanitized RFC 7807 responses without leaks."""

    def test_unhandled_exception_masks_internal_details(self) -> None:
        """Unhandled 500 error logs securely and masks stack trace from API client."""
        factory = RequestFactory()
        request = factory.get("/api/v1/simulation/runs/")

        class DummyView(APIView):
            pass

        exc = RuntimeError("Database connection string: postgres://admin:secretpass@db.internal")

        with self.assertLogs("amapp.api", level=logging.ERROR) as cm:
            resp: Response = api_exception_handler(exc, {"view": DummyView(), "request": request})

        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        data = resp.data
        self.assertIn("error", data)
        self.assertEqual(data["error"]["code"], "INTERNAL_SERVER_ERROR")
        # Ensure credentials / sensitive error details are NOT returned in response body
        self.assertNotIn("postgres://", data["error"]["message"])
        self.assertNotIn("secretpass", data["error"]["message"])
        self.assertIsNone(data["error"]["details"])

        # Ensure the error was logged server-side
        self.assertTrue(any("Unhandled server exception" in line for line in cm.output))


if __name__ == "__main__":
    unittest.main()
