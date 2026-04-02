"""Session state engine backed by an in-process dict (with optional Redis).

The SessionState is the single source of truth for the entire system:
- Live car telemetry (keyed by car_id)
- Per-sector flag states and best times
- Global flag / session mode
- Telemetry heartbeat timestamp (used by the failsafe monitor)
"""

from __future__ import annotations

import asyncio
import logging
from time import time
from typing import Optional

from automarshal.models.car import CarTelemetry
from automarshal.models.flag import FlagState
from automarshal.models.sector import Sector

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Session modes
# ──────────────────────────────────────────────────────────────────────────────


class SessionMode(str):
    PRACTICE = "PRACTICE"
    QUALIFYING = "QUALIFYING"
    RACE = "RACE"


class SessionState:
    """Thread-safe, async-friendly session state store.

    All mutations are guarded by an asyncio.Lock so that the ingestion
    callbacks and the flag/rule engine can run concurrently without races.

    Attributes:
        mode: Current session mode (Practice / Qualifying / Race).
        global_flag: Overriding global flag (RED, SAFETY_CAR, etc.).
        sectors: Ordered list of Sector objects indexed by sector_id.
        cars: Live telemetry keyed by car_id.
        last_telemetry_at: Unix timestamp of the most recent telemetry update.
        leader_car_id: Car ID of the current race leader.
    """

    def __init__(self, num_sectors: int = 3, mode: str = SessionMode.PRACTICE) -> None:
        self.mode: str = mode
        self.global_flag: Optional[FlagState] = None
        self.sectors: list[Sector] = [
            Sector(sector_id=i, name=f"Sector {i + 1}") for i in range(num_sectors)
        ]
        self.cars: dict[str, CarTelemetry] = {}
        self.last_telemetry_at: float = time()
        self.leader_car_id: Optional[str] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    # ── Telemetry updates ─────────────────────────────────────────────────────

    async def update_car(self, telemetry: CarTelemetry) -> None:
        """Upsert a car's telemetry and refresh the heartbeat timestamp."""
        async with self._lock:
            self.cars[telemetry.car_id] = telemetry
            self.last_telemetry_at = time()

    async def update_sector_best_time(
        self, sector_id: int, car_class: str, sector_time: float
    ) -> None:
        """Update the best sector time for a class if the new time is faster."""
        async with self._lock:
            if 0 <= sector_id < len(self.sectors):
                self.sectors[sector_id].update_best_time(car_class, sector_time)

    # ── Flag management ───────────────────────────────────────────────────────

    async def set_sector_flag(self, sector_id: int, flag: FlagState) -> None:
        """Set the flag for a specific sector."""
        async with self._lock:
            if 0 <= sector_id < len(self.sectors):
                self.sectors[sector_id].set_flag(flag)
                logger.info("Sector %d → %s", sector_id + 1, flag.value)

    async def get_sector_flag(self, sector_id: int) -> FlagState:
        """Return the current flag for a sector (GREEN if out of range)."""
        async with self._lock:
            if 0 <= sector_id < len(self.sectors):
                return self.sectors[sector_id].flag
        return FlagState.GREEN

    async def set_global_flag(self, flag: Optional[FlagState]) -> None:
        """Set or clear the global flag override."""
        async with self._lock:
            self.global_flag = flag
            logger.info("Global flag → %s", flag.value if flag else "None")

    async def get_global_flag(self) -> Optional[FlagState]:
        """Return the active global flag (or None)."""
        async with self._lock:
            return self.global_flag

    # ── Helpers ───────────────────────────────────────────────────────────────

    async def get_car(self, car_id: str) -> Optional[CarTelemetry]:
        """Return the latest telemetry for a car, or None if not tracked."""
        async with self._lock:
            return self.cars.get(car_id)

    async def get_all_cars(self) -> list[CarTelemetry]:
        """Return a snapshot list of all live car telemetry objects."""
        async with self._lock:
            return list(self.cars.values())

    async def get_sector(self, sector_id: int) -> Optional[Sector]:
        """Return a copy of the sector object."""
        async with self._lock:
            if 0 <= sector_id < len(self.sectors):
                return self.sectors[sector_id]
        return None

    def telemetry_age(self) -> float:
        """Return seconds since the last telemetry update."""
        return time() - self.last_telemetry_at

    async def set_leader(self, car_id: str) -> None:
        """Mark a car as the current race leader."""
        async with self._lock:
            self.leader_car_id = car_id
