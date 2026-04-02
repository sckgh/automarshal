"""GPS / X2 Link adapter (stub).

The X2 Link protocol streams 10 Hz GPS and IMU data per transponder.  In
production this module opens a TCP socket to the X2 Link server and decodes
the binary frames.  This stub provides a no-op implementation that logs a
startup message.

Replace :meth:`GPSClient.connect` internals with the real X2 Link decode
logic when the SDK library is available.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from automarshal.models.car import CarTelemetry

logger = logging.getLogger(__name__)

GPSCallback = Callable[[CarTelemetry], Awaitable[None]]


class GPSClient:
    """Interface to the Garmin / X2 Link 10 Hz GPS stream.

    Parameters:
        host: Hostname or IP of the X2 Link GPS server.
        port: TCP port for the X2 Link GPS stream.
        on_gps: Async callback invoked for each GPS frame.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4001,
        on_gps: Optional[GPSCallback] = None,
    ) -> None:
        self.host = host
        self.port = port
        self._on_gps = on_gps
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def connect(self) -> None:
        """Establish connection to the X2 Link GPS server (stub)."""
        logger.info("GPSClient: connecting to %s:%d (stub mode)", self.host, self.port)
        self._running = True
        self._task = asyncio.create_task(self._idle_loop())

    async def disconnect(self) -> None:
        """Disconnect from the GPS server."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("GPSClient: disconnected")

    async def _idle_loop(self) -> None:
        """Placeholder: real implementation decodes X2 Link binary frames."""
        while self._running:
            await asyncio.sleep(1)
