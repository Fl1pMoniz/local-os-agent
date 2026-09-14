"""Airspace ADS-B radar tracking port definitions."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class AirspaceRadarPort(Protocol):
    """Protocol for tracking commercial and general aviation flights via ADS-B telemetry."""

    def track_flight(self, query: str) -> tuple[bool, dict[str, Any]]:
        """Resolves flight details, starts active tracking, and updates cache."""
        ...

    def get_tracked_flight(self) -> dict[str, Any] | None:
        """Returns currently tracked flight telemetry dictionary, or None."""
        ...

    def refresh_flight_data(self, callsign: str) -> dict[str, Any] | None:
        """Forces an updated position and altitude fetch for the specified callsign."""
        ...
