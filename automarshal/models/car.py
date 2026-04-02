"""Car telemetry data model."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time


@dataclass
class CarTelemetry:
    """Live telemetry snapshot for a single car.

    Attributes:
        car_id: Transponder / car number (str to allow "10A" etc.).
        car_class: Racing class (e.g. "GT3", "LMP2").
        track_position: Named track position string (e.g. "Turn 4", "Sector 2").
        sector_id: Current sector index (0-based).
        velocity_kmh: Current speed in km/h (from GPS or loop delta).
        latitude: GPS latitude in decimal degrees.
        longitude: GPS longitude in decimal degrees.
        current_sector_time: Elapsed time (seconds) in the current sector.
        last_sector_time: Completed sector time for the previous sector (seconds).
        gap_to_car_ahead: Time gap in seconds to the car immediately ahead.
        timestamp: Unix timestamp of this telemetry sample.
    """

    car_id: str
    car_class: str = "UNKNOWN"
    track_position: str = ""
    sector_id: int = 0
    velocity_kmh: float = 0.0
    latitude: float = 0.0
    longitude: float = 0.0
    current_sector_time: float = 0.0
    last_sector_time: float = 0.0
    gap_to_car_ahead: float | None = None
    timestamp: float = field(default_factory=time)
