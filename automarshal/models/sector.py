"""Sector model representing a track sector and its current flag state."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import time

from automarshal.models.flag import FlagState


@dataclass
class Sector:
    """A single track sector.

    Attributes:
        sector_id: Zero-based sector index.
        name: Human-readable name (e.g. "Sector 1", "Turn 4").
        flag: Current flag state for this sector.
        best_times: Mapping of car_class -> best sector time (seconds).
        flag_set_at: Timestamp when the current flag was set (for persistence window).
        green_display_until: If set, display GREEN until this timestamp then clear.
    """

    sector_id: int
    name: str = ""
    flag: FlagState = FlagState.GREEN
    best_times: dict[str, float] = field(default_factory=dict)
    flag_set_at: float = field(default_factory=time)
    green_display_until: float | None = None

    def update_best_time(self, car_class: str, sector_time: float) -> None:
        """Record a new sector time if it is a personal/class best."""
        current_best = self.best_times.get(car_class)
        if current_best is None or sector_time < current_best:
            self.best_times[car_class] = sector_time

    def get_best_time(self, car_class: str) -> float | None:
        """Return the current best sector time for a given class."""
        return self.best_times.get(car_class)

    def set_flag(self, flag: FlagState) -> None:
        """Set the sector flag and record the timestamp."""
        self.flag = flag
        self.flag_set_at = time()
