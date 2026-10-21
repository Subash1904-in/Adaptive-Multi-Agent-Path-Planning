"""Unit tests for TelemetryRecord models, TelemetryCollector bounded retention, and drop policies.

Verifies:
- TelemetryRecord schema versioning and validation
- Invariant enforcement (non-negative tick, simulation time, required identifiers)
- Bounded capacity and non-critical event drop tracking
- Strict retention mode raising TelemetryRetentionOverflowError
- Critical event preservation via oldest non-critical eviction
- Overflow exception when buffer is saturated with critical records
- Query filtering by tick boundaries, record types, and agent IDs
- Stream finalization and closure invariants
"""

import pytest

from apps.core.telemetry.collector import TelemetryCollector
from apps.core.telemetry.exceptions import (
    TelemetryError,
    TelemetryRetentionOverflowError,
    TelemetryValidationError,
    UnsupportedSchemaError,
)
from apps.core.telemetry.models import (
    TelemetryConfig,
    TelemetryRecord,
    TelemetryRecordType,
    sanitize_for_json,
)


class TestTelemetryRecordModels:
    """Tests telemetry record data models, validation, and serialization."""

    def test_valid_record_instantiation_and_serialization(self):
        """Valid record correctly initializes and round-trips through to_dict and from_dict."""
        rec = TelemetryRecord(
            record_id="rec_001",
            run_id="run_test",
            tick_index=5,
            simulation_time_s=0.5,
            record_type=TelemetryRecordType.VEHICLE_STATE,
            name="motion_step",
            payload={"speed_mps": 8.5, "edge_id": "edge_1"},
            agent_id="veh_01",
            correlation_id="corr_abc",
            sequence_number=10,
        )
        assert rec.is_critical is False

        data = rec.to_dict()
        assert data["record_id"] == "rec_001"
        assert data["run_id"] == "run_test"
        assert data["record_type"] == "VEHICLE_STATE"
        assert data["payload"]["speed_mps"] == 8.5

        restored = TelemetryRecord.from_dict(data)
        assert restored.record_id == rec.record_id
        assert restored.run_id == rec.run_id
        assert restored.tick_index == rec.tick_index
        assert restored.record_type == rec.record_type
        assert restored.payload == rec.payload

    def test_record_validation_constraints(self):
        """Invalid fields raise TelemetryValidationError."""
        with pytest.raises(TelemetryValidationError):
            TelemetryRecord(
                record_id="",  # Empty
                run_id="run_1",
                tick_index=0,
                simulation_time_s=0.0,
                record_type=TelemetryRecordType.VEHICLE_STATE,
                name="step",
            )

        with pytest.raises(TelemetryValidationError):
            TelemetryRecord(
                record_id="r1",
                run_id="run_1",
                tick_index=-1,  # Negative tick
                simulation_time_s=0.0,
                record_type=TelemetryRecordType.VEHICLE_STATE,
                name="step",
            )

        with pytest.raises(TelemetryValidationError):
            TelemetryRecord(
                record_id="r1",
                run_id="run_1",
                tick_index=0,
                simulation_time_s=-0.1,  # Negative time
                record_type=TelemetryRecordType.VEHICLE_STATE,
                name="step",
            )

    def test_unsupported_schema_version_rejected(self):
        """Unsupported schema versions raise UnsupportedSchemaError on creation and parsing."""
        with pytest.raises(UnsupportedSchemaError):
            TelemetryRecord(
                record_id="r1",
                run_id="run_1",
                tick_index=0,
                simulation_time_s=0.0,
                record_type=TelemetryRecordType.VEHICLE_STATE,
                name="step",
                schema_version="999.0.0",
            )

        valid_dict = {
            "record_id": "r1",
            "run_id": "run_1",
            "tick_index": 0,
            "simulation_time_s": 0.0,
            "record_type": "VEHICLE_STATE",
            "name": "step",
            "payload": {},
            "schema_version": "2.0.0-unsupported",
        }
        with pytest.raises(UnsupportedSchemaError):
            TelemetryRecord.from_dict(valid_dict)

    def test_non_finite_floating_point_sanitization(self):
        """NaN, Infinity, and -Infinity are sanitized into valid RFC 8259 JSON representations."""
        raw_payload = {
            "valid_float": 3.14159,
            "positive_inf": float("inf"),
            "negative_inf": float("-inf"),
            "not_a_number": float("nan"),
            "nested": [float("inf"), {"inner_nan": float("nan")}],
        }
        sanitized = sanitize_for_json(raw_payload)
        assert sanitized["valid_float"] == 3.14159
        assert sanitized["positive_inf"] == "Infinity"
        assert sanitized["negative_inf"] == "-Infinity"
        assert sanitized["not_a_number"] == "NaN"
        assert sanitized["nested"][0] == "Infinity"
        assert sanitized["nested"][1]["inner_nan"] == "NaN"


class TestTelemetryCollectorRetentionAndDrops:
    """Tests bounded capacity, drop tracking, and critical record preservation."""

    def test_bounded_capacity_drops_noncritical_and_increments_stats(self):
        """When buffer is full, incoming non-critical records are dropped and tracked."""
        config = TelemetryConfig(max_records=3, strict_retention=False)
        collector = TelemetryCollector(run_id="run_drops", config=config)

        # Emit 3 non-critical records
        r1 = collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 0, 0.0, {})
        r2 = collector.emit(TelemetryRecordType.VEHICLE_STATE, "v2", 0, 0.0, {})
        r3 = collector.emit(TelemetryRecordType.PEDESTRIAN_STATE, "p1", 0, 0.0, {})

        assert r1 is not None and r2 is not None and r3 is not None
        assert collector.record_count == 3
        assert collector.drop_stats.total_dropped == 0

        # Emit 4th and 5th non-critical records (must be dropped)
        r4 = collector.emit(TelemetryRecordType.VEHICLE_STATE, "v4", 1, 0.1, {})
        r5 = collector.emit(TelemetryRecordType.PEDESTRIAN_STATE, "p2", 1, 0.1, {})

        assert r4 is None
        assert r5 is None
        assert collector.record_count == 3
        assert collector.drop_stats.total_dropped == 2
        assert collector.drop_stats.dropped_by_category["VEHICLE_STATE"] == 1
        assert collector.drop_stats.dropped_by_category["PEDESTRIAN_STATE"] == 1

    def test_strict_retention_raises_overflow_error(self):
        """When strict_retention=True, reaching capacity raises TelemetryRetentionOverflowError."""
        config = TelemetryConfig(max_records=2, strict_retention=True)
        collector = TelemetryCollector(run_id="run_strict", config=config)

        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 0, 0.0, {})
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v2", 0, 0.0, {})

        with pytest.raises(TelemetryRetentionOverflowError) as exc_info:
            collector.emit(TelemetryRecordType.VEHICLE_STATE, "v3", 1, 0.1, {})
        assert exc_info.value.capacity == 2

    def test_critical_event_preservation_evicts_oldest_noncritical(self):
        """A critical event evicts the oldest non-critical record rather than dropping."""
        config = TelemetryConfig(max_records=2, strict_retention=False)
        collector = TelemetryCollector(run_id="run_critical", config=config)

        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 0, 0.0, {"step": 1})
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v2", 0, 0.0, {"step": 2})
        assert collector.record_count == 2
        assert collector.drop_stats.total_dropped == 0

        # Critical event arrives (SAFETY_EVENT)
        crit_record = collector.emit(
            TelemetryRecordType.SAFETY_EVENT,
            "emergency_brake",
            1,
            0.1,
            {"hazard": "proximity"},
        )
        assert crit_record is not None
        assert collector.record_count == 2
        assert collector.drop_stats.total_dropped == 1
        assert collector.drop_stats.dropped_by_category["VEHICLE_STATE"] == 1

        retained = collector.get_records()
        types = [r.record_type for r in retained]
        assert TelemetryRecordType.SAFETY_EVENT in types
        assert retained[0].payload.get("step") == 2  # first record (step 1) was evicted

    def test_buffer_saturated_with_critical_events_raises_overflow(self):
        """When buffer is saturated with critical records, adding another raises overflow."""
        config = TelemetryConfig(max_records=2, strict_retention=False)
        collector = TelemetryCollector(run_id="run_sat", config=config)

        collector.emit(TelemetryRecordType.SAFETY_EVENT, "safety_1", 0, 0.0, {})
        collector.emit(TelemetryRecordType.COLLISION_EVENT, "collision_1", 1, 0.1, {})
        assert collector.record_count == 2

        # 3rd critical event cannot evict any non-critical record
        with pytest.raises(TelemetryRetentionOverflowError):
            collector.emit(TelemetryRecordType.ERROR, "fatal_error", 2, 0.2, {})

    def test_category_filtering(self):
        """Records from disabled categories are ignored unless critical."""
        config = TelemetryConfig(
            max_records=10,
            enabled_categories=frozenset({TelemetryRecordType.VEHICLE_STATE}),
        )
        collector = TelemetryCollector(run_id="run_filt", config=config)

        # Vehicle state enabled
        r_veh = collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 0, 0.0, {})
        assert r_veh is not None

        # Pedestrian state disabled
        r_ped = collector.emit(TelemetryRecordType.PEDESTRIAN_STATE, "p1", 0, 0.0, {})
        assert r_ped is None

        # Safety event is critical: must be recorded even if not in enabled_categories
        r_safety = collector.emit(TelemetryRecordType.SAFETY_EVENT, "safe1", 0, 0.0, {})
        assert r_safety is not None
        assert collector.record_count == 2

    def test_stream_closure_rejects_further_records(self):
        """Closing the telemetry stream prevents any subsequent emissions."""
        collector = TelemetryCollector(run_id="run_closed")
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 0, 0.0, {})
        assert not collector.is_closed

        collector.close()
        assert collector.is_closed

        with pytest.raises(TelemetryError):
            collector.emit(TelemetryRecordType.VEHICLE_STATE, "v2", 1, 0.1, {})

    def test_filter_records_and_get_recent(self):
        """Query filtering by tick range, category, and agent ID works accurately."""
        collector = TelemetryCollector(run_id="run_query")
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 1, 0.1, {}, agent_id="veh_01")
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v2", 1, 0.1, {}, agent_id="veh_02")
        collector.emit(TelemetryRecordType.VEHICLE_STATE, "v1", 2, 0.2, {}, agent_id="veh_01")
        collector.emit(TelemetryRecordType.ROUTE_CHANGE, "r1", 2, 0.2, {}, agent_id="veh_01")

        # Filter by tick
        tick_1_recs = collector.filter_records(min_tick=1, max_tick=1)
        assert len(tick_1_recs) == 2

        # Filter by agent
        veh_02_recs = collector.filter_records(agent_id="veh_02")
        assert len(veh_02_recs) == 1
        assert veh_02_recs[0].agent_id == "veh_02"

        # Filter by category
        route_recs = collector.filter_records(categories={TelemetryRecordType.ROUTE_CHANGE})
        assert len(route_recs) == 1

        # Recent N
        recent_2 = collector.get_recent(count=2)
        assert len(recent_2) == 2
        assert recent_2[-1].record_type == TelemetryRecordType.ROUTE_CHANGE
