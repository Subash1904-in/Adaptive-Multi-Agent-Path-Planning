"""Simulation Telemetry, Stream Retention, Fingerprinting, and Metrics Aggregation Subsystem.

Provides unified event observation, deterministic hashing and reproducibility metadata,
bounded in-process stream retention, drop tracking, non-finite numeric sanitization, and
cross-subsystem metrics summaries for the AMAPP simulation platform.
"""

from apps.core.telemetry.aggregation import (
    METRIC_CLASSIFICATIONS,
    MetricsAggregator,
    RunMetricsSummary,
)
from apps.core.telemetry.collector import TelemetryCollector
from apps.core.telemetry.exceptions import (
    CancellationError,
    DuplicateRunIdError,
    ExportSizeLimitExceededError,
    InvalidExecutionLimitsError,
    InvalidMetricValueError,
    RunStateTransitionError,
    ScenarioFinalizationError,
    TelemetryError,
    TelemetryRetentionOverflowError,
    TelemetryValidationError,
    UnsupportedSchemaError,
)
from apps.core.telemetry.fingerprint import (
    canonical_json_dumps,
    compute_scenario_fingerprint,
    compute_sha256_digest,
    compute_world_state_fingerprint,
    get_git_commit_sha,
)
from apps.core.telemetry.models import (
    CRITICAL_RECORD_TYPES,
    SUPPORTED_SCHEMA_VERSIONS,
    TELEMETRY_SCHEMA_VERSION,
    TelemetryConfig,
    TelemetryDropStats,
    TelemetryRecord,
    TelemetryRecordType,
    sanitize_for_json,
)

__all__ = [
    # Schema and Config
    "TELEMETRY_SCHEMA_VERSION",
    "SUPPORTED_SCHEMA_VERSIONS",
    "TelemetryRecordType",
    "CRITICAL_RECORD_TYPES",
    "TelemetryRecord",
    "TelemetryConfig",
    "TelemetryDropStats",
    "sanitize_for_json",
    # Stream Collector
    "TelemetryCollector",
    # Hashing & Fingerprinting
    "canonical_json_dumps",
    "compute_sha256_digest",
    "compute_scenario_fingerprint",
    "compute_world_state_fingerprint",
    "get_git_commit_sha",
    # Metrics Aggregation
    "METRIC_CLASSIFICATIONS",
    "RunMetricsSummary",
    "MetricsAggregator",
    # Exceptions
    "TelemetryError",
    "TelemetryValidationError",
    "UnsupportedSchemaError",
    "TelemetryRetentionOverflowError",
    "ExportSizeLimitExceededError",
    "RunStateTransitionError",
    "InvalidExecutionLimitsError",
    "CancellationError",
    "DuplicateRunIdError",
    "ScenarioFinalizationError",
    "InvalidMetricValueError",
]
