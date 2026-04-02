"""Tests for the radio controller and handshake state machine."""

from __future__ import annotations

import asyncio

import pytest

from automarshal.models.flag import FlagState
from automarshal.radio.radio_controller import RadioController, HandshakeState
from automarshal.radio.stt_engine import STTEngine
from automarshal.radio.tts_engine import TTSEngine


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _make_controller(stt_response: str = "Go ahead Sector 1") -> RadioController:
    tts = TTSEngine(speaking_rate_wps=100.0)   # fast for tests
    stt = STTEngine(simulated_response=stt_response, listen_timeout_s=0.01)
    return RadioController(tts=tts, stt=stt)


# ──────────────────────────────────────────────────────────────────────────────
# Driver channel
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_driver_broadcast_red_flag():
    ctrl = _make_controller()
    await ctrl.start()
    try:
        await ctrl.driver_broadcast("RED FLAG. RED FLAG. RETURN TO PITS.", FlagState.RED)
        # Give the consumer a moment to process
        await asyncio.sleep(0.2)
    finally:
        await ctrl.stop()


@pytest.mark.asyncio
async def test_driver_broadcast_blue_flag_suppressed():
    ctrl = _make_controller()
    await ctrl.start()
    try:
        # Blue flag audio must be silently discarded
        await ctrl.driver_broadcast("Blue flag. Car approaching.", FlagState.BLUE)
        await asyncio.sleep(0.1)
        # Queue should remain empty after the suppression
        assert ctrl._driver_queue.empty()
    finally:
        await ctrl.stop()


@pytest.mark.asyncio
async def test_driver_priority_ordering():
    """Higher-priority messages should appear first in the queue."""
    ctrl = _make_controller()
    # Manually enqueue without starting the consumer
    await ctrl.driver_broadcast("Yellow message.", FlagState.YELLOW)
    await ctrl.driver_broadcast("Red message.", FlagState.RED)

    # Red (priority 0) should be dequeued before Yellow (priority 2)
    first = await ctrl._driver_queue.get()
    second = await ctrl._driver_queue.get()
    assert first.flag == FlagState.RED
    assert second.flag == FlagState.YELLOW


# ──────────────────────────────────────────────────────────────────────────────
# Race Control handshake
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handshake_success():
    """A correct ACK should allow the detail message to be transmitted."""
    stt = STTEngine(simulated_response="Go ahead Sector 1", listen_timeout_s=0.01)
    tts = TTSEngine(speaking_rate_wps=500.0, min_duration_s=0.0)
    ctrl = RadioController(tts=tts, stt=stt)
    await ctrl.start()
    try:
        await ctrl.rc_incident(sector_id=0, detail="Car 42 traveling slowly.")
        # Allow time for the handshake coroutine to complete
        await asyncio.sleep(0.5)
        assert ctrl.rc_state == HandshakeState.IDLE
    finally:
        await ctrl.stop()


@pytest.mark.asyncio
async def test_handshake_bad_ack_aborts():
    """A wrong ACK response should abort the handshake cleanly."""
    stt = STTEngine(simulated_response="Something else entirely", listen_timeout_s=0.01)
    tts = TTSEngine(speaking_rate_wps=500.0, min_duration_s=0.0)
    ctrl = RadioController(tts=tts, stt=stt)
    await ctrl.start()
    try:
        await ctrl.rc_incident(sector_id=0, detail="Car 42 stopped.")
        await asyncio.sleep(0.5)
        assert ctrl.rc_state == HandshakeState.IDLE
    finally:
        await ctrl.stop()


# ──────────────────────────────────────────────────────────────────────────────
# Safety Car loop
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_safety_car_loop_starts_and_stops():
    ctrl = _make_controller()
    await ctrl.start()
    try:
        await ctrl.start_safety_car_loop()
        assert ctrl._sc_task is not None
        await ctrl.stop_safety_car_loop()
        assert ctrl._sc_task is None
    finally:
        await ctrl.stop()
