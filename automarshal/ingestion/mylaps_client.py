"""MyLaps SDK adapter (stub).

In production this module wraps the Orbits / X2 SDK library to subscribe to
Passing events (timing loop crossings) and 10 Hz GPS/IMU telemetry.  The
stub here generates synthetic data for development and testing purposes.

The real SDK integration point is :meth:`MyLapsClient.connect` – replace the
``_simulate_*`` internals with actual SDK callbacks.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Callable, Awaitable, Optional

from automarshal.models.car import CarTelemetry

logger = logging.getLogger(__name__)

TelemetryCallback = Callable[[CarTelemetry], Awaitable[None]]


class MyLapsClient:
    """Interface to the MyLaps X2 / Orbits timing system.

    In a real deployment the SDK fires callbacks when transponders pass timing
    loops.  This stub simulates that behaviour with randomised telemetry.

    Parameters:
        host: Hostname or IP of the Orbits PC / X2 Link server.
        port: TCP port for the X2 SDK connection.
        on_telemetry: Async callback invoked for every new telemetry frame.
        num_cars: (stub only) Number of simulated cars.
        num_sectors: (stub only) Number of simulated track sectors.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4000,
        on_telemetry: Optional[TelemetryCallback] = None,
        num_cars: int = 5,
        num_sectors: int = 3,
    ) -> None:
        self.host = host
        self.port = port
        self._on_telemetry = on_telemetry
        self._num_cars = num_cars
        self._num_sectors = num_sectors
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Establish connection (stub: starts the simulation loop)."""
        logger.info(
            "MyLapsClient: connecting to %s:%d (stub mode)", self.host, self.port
        )
        self._running = True
        self._task = asyncio.create_task(self._simulate_loop())

    async def disconnect(self) -> None:
        """Gracefully disconnect from the timing system."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MyLapsClient: disconnected")

    # ── Stub simulation ───────────────────────────────────────────────────────

    async def _simulate_loop(self) -> None:
        """Generate synthetic 10 Hz telemetry frames for *num_cars* cars."""
        car_ids = [str(i + 1) for i in range(self._num_cars)]
        classes = ["GT3", "GT4", "LMP2"]
        sector_names = [f"Sector {i + 1}" for i in range(self._num_sectors)]

        # Accumulate per-car elapsed sector time
        elapsed: dict[str, float] = {cid: 0.0 for cid in car_ids}

        while self._running:
            for car_id in car_ids:
                elapsed[car_id] += 0.1  # 10 Hz
                telemetry = CarTelemetry(
                    car_id=car_id,
                    car_class=classes[int(car_id) % len(classes)],
                    track_position=sector_names[int(car_id) % self._num_sectors],
                    sector_id=int(car_id) % self._num_sectors,
                    velocity_kmh=random.uniform(80, 160),
                    latitude=51.5 + random.uniform(-0.01, 0.01),
                    longitude=-0.1 + random.uniform(-0.01, 0.01),
                    current_sector_time=elapsed[car_id],
                    last_sector_time=random.uniform(20, 40),
                    gap_to_car_ahead=random.uniform(0.5, 10.0),
                )
                if self._on_telemetry:
                    await self._on_telemetry(telemetry)

            await asyncio.sleep(0.1)  # 10 Hz
