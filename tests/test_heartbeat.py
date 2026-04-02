"""Tests for the heartbeat / failsafe monitor."""

from __future__ import annotations

import asyncio
from time import time
from unittest.mock import AsyncMock

import pytest

from automarshal.engine.session_state import SessionState
from automarshal.models.car import CarTelemetry
from automarshal.models.flag import FlagState
from automarshal.safety.heartbeat import HeartbeatMonitor


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_monitor(state: SessionState, timeout_ms: int = 200):
    on_failsafe = AsyncMock()
    monitor = HeartbeatMonitor(state=state, timeout_ms=timeout_ms, on_failsafe=on_failsafe)
    return monitor, on_failsafe


# ──────────────────────────────────────────────────────────────────────────────
# Failsafe activation
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_failsafe_activates_on_stale_telemetry():
    """Failsafe should trigger if no telemetry arrives within the timeout."""
    state = SessionState(num_sectors=2)
    monitor, on_failsafe = _make_monitor(state, timeout_ms=100)

    await monitor.start()
    try:
        # Do NOT update telemetry – let it go stale
        await asyncio.sleep(0.4)
        assert monitor.failsafe_active is True
        on_failsafe.assert_awaited_with(True)
        global_flag = await state.get_global_flag()
        assert global_flag == FlagState.MANUAL_ONLY
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_failsafe_clears_when_telemetry_resumes():
    """Failsafe should clear once fresh telemetry arrives."""
    state = SessionState(num_sectors=2)
    monitor, on_failsafe = _make_monitor(state, timeout_ms=100)

    await monitor.start()
    try:
        # Let failsafe activate
        await asyncio.sleep(0.4)
        assert monitor.failsafe_active is True

        # Keep injecting fresh telemetry every 50 ms so age stays below threshold
        for _ in range(6):
            car = CarTelemetry(car_id="1")
            await state.update_car(car)
            await asyncio.sleep(0.05)

        assert monitor.failsafe_active is False
        on_failsafe.assert_any_await(False)
    finally:
        await monitor.stop()


@pytest.mark.asyncio
async def test_failsafe_does_not_activate_with_fresh_telemetry():
    """No failsafe when telemetry arrives faster than the timeout."""
    state = SessionState(num_sectors=2)
    monitor, on_failsafe = _make_monitor(state, timeout_ms=500)

    await monitor.start()
    try:
        # Keep feeding telemetry every 50 ms for 300 ms
        for _ in range(6):
            car = CarTelemetry(car_id="1")
            await state.update_car(car)
            await asyncio.sleep(0.05)
        assert monitor.failsafe_active is False
        on_failsafe.assert_not_awaited()
    finally:
        await monitor.stop()


# ──────────────────────────────────────────────────────────────────────────────
# telemetry_age
# ──────────────────────────────────────────────────────────────────────────────


def test_telemetry_age_increases_over_time():
    state = SessionState()
    import time as time_module
    time_module.sleep(0.05)
    age = state.telemetry_age()
    assert age >= 0.05
