"""Heartbeat / failsafe monitor.

If no telemetry has been received within :attr:`HeartbeatMonitor.timeout_ms`
milliseconds the monitor transitions all flag panels to the ``MANUAL_ONLY``
state and logs a critical alert.  When telemetry resumes the system returns
to automatic mode.

The 500 ms threshold is specified in the problem statement.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable, Awaitable, Optional

from automarshal.engine.session_state import SessionState
from automarshal.models.flag import FlagState

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_MS = 500   # Telemetry must arrive within this window
CHECK_INTERVAL_S = 0.1     # How often to poll for stale telemetry

OnFailsafeCallback = Callable[[bool], Awaitable[None]]


class HeartbeatMonitor:
    """Monitor telemetry freshness and assert MANUAL_ONLY on timeout.

    Parameters:
        state: Shared :class:`~automarshal.engine.session_state.SessionState`.
        timeout_ms: Milliseconds before a telemetry gap triggers failsafe mode.
        on_failsafe: Optional async callback invoked with ``True`` when failsafe
            is activated and ``False`` when it is cleared.
    """

    def __init__(
        self,
        state: SessionState,
        timeout_ms: int = DEFAULT_TIMEOUT_MS,
        on_failsafe: Optional[OnFailsafeCallback] = None,
    ) -> None:
        self._state = state
        self._timeout_s = timeout_ms / 1000.0
        self._on_failsafe = on_failsafe
        self._failsafe_active = False
        self._task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Begin monitoring telemetry latency."""
        self._task = asyncio.create_task(self._monitor_loop(), name="heartbeat")
        logger.info(
            "HeartbeatMonitor started (timeout=%.0f ms)", self._timeout_s * 1000
        )

    async def stop(self) -> None:
        """Stop the heartbeat monitor."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("HeartbeatMonitor stopped")

    @property
    def failsafe_active(self) -> bool:
        """True if the system is currently in MANUAL_ONLY failsafe mode."""
        return self._failsafe_active

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _monitor_loop(self) -> None:
        while True:
            await asyncio.sleep(CHECK_INTERVAL_S)
            age = self._state.telemetry_age()

            if age > self._timeout_s and not self._failsafe_active:
                await self._activate_failsafe(age)
            elif age <= self._timeout_s and self._failsafe_active:
                await self._clear_failsafe()

    async def _activate_failsafe(self, age_s: float) -> None:
        """Assert MANUAL_ONLY on all sectors."""
        self._failsafe_active = True
        logger.critical(
            "FAILSAFE: Telemetry age %.0f ms exceeds %.0f ms threshold – "
            "switching to MANUAL ONLY.",
            age_s * 1000, self._timeout_s * 1000,
        )
        await self._state.set_global_flag(FlagState.MANUAL_ONLY)
        for i in range(len(self._state.sectors)):
            await self._state.set_sector_flag(i, FlagState.MANUAL_ONLY)
        if self._on_failsafe:
            await self._on_failsafe(True)

    async def _clear_failsafe(self) -> None:
        """Return to automatic mode when telemetry is restored."""
        self._failsafe_active = False
        logger.warning("FAILSAFE CLEARED: Telemetry restored – resuming automatic mode.")
        await self._state.set_global_flag(None)
        for i in range(len(self._state.sectors)):
            await self._state.set_sector_flag(i, FlagState.GREEN)
        if self._on_failsafe:
            await self._on_failsafe(False)
