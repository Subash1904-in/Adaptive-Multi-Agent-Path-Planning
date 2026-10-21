"""In-process bounded telemetry collection and stream retention engine.

Enforces deterministic record sequencing, bounded buffer capacities, priority-based
critical event retention (safety, collision, error, run-terminal), drop counter tracking,
and multi-attribute query filtering.
"""

import logging
from typing import Any, Callable, Iterable, Optional, Union

from apps.core.telemetry.exceptions import (
    TelemetryError,
    TelemetryRetentionOverflowError,
    TelemetryValidationError,
)
from apps.core.telemetry.models import (
    TelemetryConfig,
    TelemetryDropStats,
    TelemetryRecord,
    TelemetryRecordType,
)

logger = logging.getLogger("amapp.telemetry")


class TelemetryCollector:
    """In-process bounded collector for simulation telemetry observations."""

    def __init__(self, run_id: str, config: Optional[TelemetryConfig] = None) -> None:
        """Initialize collector for a specific scenario run.

        Args:
            run_id: Unique identifier for the simulation run.
            config: Optional TelemetryConfig governing limits and retention policies.
        """
        if not run_id:
            raise TelemetryValidationError("run_id must be a non-empty string.", field="run_id")
        self.run_id = run_id
        self.config = config or TelemetryConfig()
        self._records: list[TelemetryRecord] = []
        self._drop_stats = TelemetryDropStats()
        self._is_closed: bool = False
        self._sequence_counter: int = 0
        self._listeners: list[Callable[[TelemetryRecord], None]] = []

    @property
    def is_closed(self) -> bool:
        """Whether the telemetry stream has been finalized and closed to new records."""
        return self._is_closed

    @property
    def drop_stats(self) -> TelemetryDropStats:
        """Drop counters detailing discarded noncritical telemetry records."""
        return self._drop_stats

    @property
    def record_count(self) -> int:
        """Total number of telemetry records currently retained in memory."""
        return len(self._records)

    def _next_sequence(self) -> int:
        """Increment and return the next sequential index for ordering within the run."""
        seq = self._sequence_counter
        self._sequence_counter += 1
        return seq

    def record(self, record: TelemetryRecord) -> bool:
        """Add an observation record to the bounded stream buffer.

        Args:
            record: The TelemetryRecord to retain.

        Returns:
            True if the record was successfully stored; False if discarded by category or capacity.

        Raises:
            TelemetryError: If the collector is already closed.
            TelemetryValidationError: If the record run_id does not match the collector run_id.
            TelemetryRetentionOverflowError: If strict retention is set or critical buffer
                capacity is exhausted.
        """
        if self._is_closed:
            raise TelemetryError(
                f"Cannot record to finalized telemetry stream for run '{self.run_id}'.",
                run_id=self.run_id,
            )

        if record.run_id != self.run_id:
            raise TelemetryValidationError(
                f"Record run_id '{record.run_id}' does not match collector run_id '{self.run_id}'.",
                field="run_id",
                run_id=self.run_id,
            )

        # 1. Check if category is enabled in config
        if not self.config.is_category_enabled(record.record_type):
            return False

        # 2. Check capacity limits
        if len(self._records) >= self.config.max_records:
            if self.config.strict_retention:
                raise TelemetryRetentionOverflowError(
                    f"Telemetry buffer reached capacity {self.config.max_records} "
                    f"with strict retention.",
                    capacity=self.config.max_records,
                    run_id=self.run_id,
                )

            # Critical records must NEVER be dropped if non-critical records can be evicted
            if record.is_critical:
                evicted_index: Optional[int] = None
                for idx, existing in enumerate(self._records):
                    if not existing.is_critical:
                        evicted_index = idx
                        break

                if evicted_index is not None:
                    evicted = self._records.pop(evicted_index)
                    cat_name = (
                        evicted.record_type.value
                        if hasattr(evicted.record_type, "value")
                        else str(evicted.record_type)
                    )
                    self._drop_stats.record_drop(cat_name)
                else:
                    raise TelemetryRetentionOverflowError(
                        f"Telemetry buffer is completely saturated with critical records "
                        f"({self.config.max_records}). Cannot retain critical event "
                        f"'{record.record_type.value}'.",
                        capacity=self.config.max_records,
                        run_id=self.run_id,
                    )
            else:
                # Discard incoming non-critical record and track drop
                cat_name = (
                    record.record_type.value
                    if hasattr(record.record_type, "value")
                    else str(record.record_type)
                )
                self._drop_stats.record_drop(cat_name)
                return False

        self._records.append(record)
        for listener in list(self._listeners):
            try:
                listener(record)
            except Exception as exc:
                logger.warning(
                    "Telemetry listener error for run '%s': %s",
                    self.run_id,
                    exc,
                )
        return True

    def add_listener(self, listener: Callable[[TelemetryRecord], None]) -> None:
        """Register a callback invoked whenever a telemetry record is stored."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[TelemetryRecord], None]) -> None:
        """Unregister a previously registered telemetry callback."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def emit(
        self,
        record_type: TelemetryRecordType,
        name: str,
        tick_index: int,
        simulation_time_s: float,
        payload: dict[str, Any],
        agent_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[TelemetryRecord]:
        """Convenience factory to create and record an observation.

        Returns:
            The created TelemetryRecord if stored, or None if dropped/disabled.
        """
        seq = self._next_sequence()
        rec_id = f"{self.run_id}_t{tick_index}_s{seq}"
        record = TelemetryRecord(
            record_id=rec_id,
            run_id=self.run_id,
            tick_index=tick_index,
            simulation_time_s=simulation_time_s,
            record_type=record_type,
            name=name,
            payload=payload,
            agent_id=agent_id,
            correlation_id=correlation_id,
            schema_version=self.config.schema_version,
            sequence_number=seq,
        )
        stored = self.record(record)
        return record if stored else None

    def filter_records(
        self,
        min_tick: Optional[int] = None,
        max_tick: Optional[int] = None,
        categories: Optional[Iterable[Union[TelemetryRecordType, str]]] = None,
        agent_id: Optional[str] = None,
    ) -> list[TelemetryRecord]:
        """Retrieve a filtered, ordered slice of retained records.

        Args:
            min_tick: Optional minimum inclusive tick index.
            max_tick: Optional maximum inclusive tick index.
            categories: Optional collection of record types to match.
            agent_id: Optional agent identifier to match.

        Returns:
            List of matching TelemetryRecords ordered by sequence.
        """
        cat_set = (
            {c.value if isinstance(c, TelemetryRecordType) else str(c) for c in categories}
            if categories is not None
            else None
        )

        results: list[TelemetryRecord] = []
        for r in self._records:
            if min_tick is not None and r.tick_index < min_tick:
                continue
            if max_tick is not None and r.tick_index > max_tick:
                continue
            if cat_set is not None:
                r_type = (
                    r.record_type.value if hasattr(r.record_type, "value") else str(r.record_type)
                )
                if r_type not in cat_set:
                    continue
            if agent_id is not None and r.agent_id != agent_id:
                continue
            results.append(r)

        return results

    def get_recent(self, count: int = 100) -> list[TelemetryRecord]:
        """Retrieve up to the N most recent telemetry records."""
        if count <= 0:
            return []
        return self._records[-count:]

    def get_records(self) -> tuple[TelemetryRecord, ...]:
        """Return an immutable snapshot of all currently retained records."""
        return tuple(self._records)

    def close(self) -> None:
        """Finalize and close the stream. Subsequent record attempts will raise TelemetryError."""
        self._is_closed = True

    def clear(self) -> None:
        """Clear all retained records and drop stats for a state reset."""
        self._records.clear()
        self._drop_stats = TelemetryDropStats()
        self._is_closed = False
        self._sequence_counter = 0
