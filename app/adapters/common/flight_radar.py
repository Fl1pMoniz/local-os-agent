"""Cross-platform airspace radar adapter implementing AirspaceRadarPort."""

from __future__ import annotations

from typing import Any

from app.ports.flight import AirspaceRadarPort


class FlightRadarAdapter(AirspaceRadarPort):
    """ADS-B radar tracking adapter connecting to FlightRadar24 or local mock telemetry."""

    def track_flight(self, query: str) -> tuple[bool, dict[str, Any]]:
        """Tracks the specified flight query and returns status telemetry."""
        from tools import flight

        clean = flight.clean_flight_query(query)
        if not clean:
            return False, {"error": "Invalid flight callsign or number."}

        data = flight.lookup_flight(clean)
        if not data:
            return False, {"error": f"Flight {clean} not found in airspace telemetry."}

        from ui.state import ui_state

        ui_state.update(tracked_flight=data)
        return True, data

    def get_tracked_flight(self) -> dict[str, Any] | None:
        """Retrieves currently tracked flight telemetry from state."""
        from tools import flight

        return flight.get_tracked_flight()

    def refresh_flight_data(self, callsign: str) -> dict[str, Any] | None:
        """Forces an updated position and altitude fetch for the specified callsign."""
        from tools import flight

        return flight.refresh_flight_data(callsign)
