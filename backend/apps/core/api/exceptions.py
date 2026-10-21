"""API exception taxonomy and custom Django REST Framework exception handler.

Translates domain exceptions, validation failures, and lifecycle conflicts into
consistent, documented RFC 7807 inspired JSON error payloads:
{
    "error": {
        "code": "ERROR_CODE",
        "message": "Human-readable explanation.",
        "details": ...
    }
}
"""

import logging
from typing import Any, Optional

from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    MethodNotAllowed,
    NotAuthenticated,
    NotFound,
    ParseError,
    PermissionDenied,
    UnsupportedMediaType,
)
from rest_framework.exceptions import (
    ValidationError as DRFValidationError,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler

from apps.core.domain.exceptions import DomainException
from apps.core.scenarios.exceptions import (
    ScenarioError,
    ScenarioValidationError,
    UnreachableDestinationError,
)
from apps.core.telemetry.exceptions import (
    CancellationError,
    DuplicateRunIdError,
    ExportSizeLimitExceededError,
    InvalidExecutionLimitsError,
    InvalidMetricValueError,
    RunStateTransitionError,
    TelemetryError,
    TelemetryRetentionOverflowError,
    UnsupportedSchemaError,
)

logger = logging.getLogger("amapp.api")


class ApiException(DomainException):
    """Base exception for REST API application layer errors."""

    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "API_ERROR"

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Any] = None,
        status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.error_code
        self.details = details
        if status_code is not None:
            self.status_code = status_code


class ScenarioNotFoundError(ApiException):
    """Raised when a requested scenario ID does not exist in the registry."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "SCENARIO_NOT_FOUND"

    def __init__(self, scenario_id: str) -> None:
        super().__init__(
            f"Scenario with ID '{scenario_id}' was not found.",
            error_code=self.error_code,
            details={"scenario_id": scenario_id},
        )
        self.scenario_id = scenario_id


class RunNotFoundError(ApiException):
    """Raised when a requested simulation run ID does not exist in the registry."""

    status_code = status.HTTP_404_NOT_FOUND
    error_code = "RUN_NOT_FOUND"

    def __init__(self, run_id: str) -> None:
        super().__init__(
            f"Simulation run with ID '{run_id}' was not found.",
            error_code=self.error_code,
            details={"run_id": run_id},
        )
        self.run_id = run_id


class DuplicateScenarioIdError(ApiException):
    """Raised when attempting to register a scenario with an existing ID."""

    status_code = status.HTTP_409_CONFLICT
    error_code = "DUPLICATE_SCENARIO_ID"

    def __init__(self, scenario_id: str) -> None:
        super().__init__(
            f"Scenario with ID '{scenario_id}' already exists in registry.",
            error_code=self.error_code,
            details={"scenario_id": scenario_id},
        )
        self.scenario_id = scenario_id


def format_error_response(
    code: str,
    message: str,
    details: Optional[Any] = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """Helper to generate a consistent JSON error Response."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
        }
    }
    return Response(payload, status=status_code)


def api_exception_handler(exc: Exception, context: dict[str, Any]) -> Optional[Response]:
    """Custom exception handler for Django REST Framework.

    Converts domain exceptions and framework errors into the standard AMAPP
    JSON error format with appropriate HTTP status codes.
    """
    view = context.get("view")
    view_name = view.__class__.__name__ if view else "UnknownView"

    # 1. Custom API Exceptions
    if isinstance(exc, ApiException):
        return format_error_response(
            code=exc.error_code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )

    # 2. Lifecycle State Transition Conflicts (HTTP 409)
    if isinstance(exc, RunStateTransitionError):
        return format_error_response(
            code="LIFECYCLE_CONFLICT",
            message=str(exc),
            details={
                "current_state": getattr(exc, "current_state", None),
                "target_state": getattr(exc, "target_state", None),
            },
            status_code=status.HTTP_409_CONFLICT,
        )

    # 3. Duplicate Resource Conflicts (HTTP 409)
    if isinstance(exc, DuplicateRunIdError):
        return format_error_response(
            code="DUPLICATE_RUN_ID",
            message=str(exc),
            details={"run_id": exc.run_id},
            status_code=status.HTTP_409_CONFLICT,
        )

    # 4. Export Size Limit Exceeded (HTTP 413)
    if isinstance(exc, ExportSizeLimitExceededError):
        return format_error_response(
            code="EXPORT_SIZE_LIMIT_EXCEEDED",
            message=str(exc),
            details={
                "size_bytes": exc.size_bytes,
                "max_bytes": exc.max_bytes,
                "run_id": exc.run_id,
            },
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    # 5. Invalid Execution Limits (HTTP 400)
    if isinstance(exc, InvalidExecutionLimitsError):
        return format_error_response(
            code="INVALID_EXECUTION_LIMITS",
            message=str(exc),
            details={"field": exc.field},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 6. Scenario Validation Errors (HTTP 400)
    if isinstance(exc, ScenarioValidationError):
        return format_error_response(
            code="VALIDATION_ERROR",
            message=str(exc),
            details=exc.details,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 7. Unreachable Destination Errors (HTTP 400)
    if isinstance(exc, UnreachableDestinationError):
        return format_error_response(
            code="UNREACHABLE_DESTINATION",
            message=str(exc),
            details=exc.details,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 8. Telemetry Retention / Schema Errors (HTTP 400)
    if isinstance(exc, (TelemetryRetentionOverflowError, UnsupportedSchemaError)):
        return format_error_response(
            code="TELEMETRY_ERROR",
            message=str(exc),
            details=getattr(exc, "details", None),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 9. Generic Domain Exceptions (HTTP 400)
    domain_exc_types = (
        DomainException,
        ScenarioError,
        TelemetryError,
        CancellationError,
        InvalidMetricValueError,
    )
    if isinstance(exc, domain_exc_types):
        return format_error_response(
            code="DOMAIN_ERROR",
            message=str(exc),
            details=getattr(exc, "details", None),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 10. Django Http404 or DRF NotFound (HTTP 404)
    if isinstance(exc, (Http404, NotFound)):
        return format_error_response(
            code="NOT_FOUND",
            message=str(exc) or "The requested resource was not found.",
            details=None,
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 11. DRF Validation Errors (HTTP 400)
    if isinstance(exc, DRFValidationError):
        msg = "Validation failed for one or more fields."
        return format_error_response(
            code="VALIDATION_ERROR",
            message=msg,
            details=exc.detail,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 12. DRF Authentication & Permission Exceptions
    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        return format_error_response(
            code="UNAUTHORIZED",
            message=str(exc) or "Authentication credentials were not provided or are invalid.",
            details=None,
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    if isinstance(exc, PermissionDenied):
        return format_error_response(
            code="PERMISSION_DENIED",
            message=str(exc) or "You do not have permission to perform this action.",
            details=None,
            status_code=status.HTTP_403_FORBIDDEN,
        )
    if isinstance(exc, MethodNotAllowed):
        return format_error_response(
            code="METHOD_NOT_ALLOWED",
            message=str(exc),
            details={"method": getattr(exc, "method", None)},
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        )
    if isinstance(exc, UnsupportedMediaType):
        return format_error_response(
            code="UNSUPPORTED_MEDIA_TYPE",
            message=str(exc),
            details=None,
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )
    if isinstance(exc, ParseError):
        return format_error_response(
            code="PARSE_ERROR",
            message=f"Malformed request payload: {exc}",
            details=None,
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 13. Fallback to standard DRF exception handler
    response = exception_handler(exc, context)
    if response is not None:
        return format_error_response(
            code="API_ERROR",
            message="An API error occurred.",
            details=response.data,
            status_code=response.status_code,
        )

    # 14. Unhandled server errors (HTTP 500)
    # Log securely without leaking secrets or sending stack traces to the client
    logger.exception("Unhandled server exception in %s: %s", view_name, exc)
    return format_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred while processing the simulation request.",
        details=None,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
