"""Tests for the flag engine."""

from __future__ import annotations

import asyncio
from typing import Optional
from unittest.mock import AsyncMock

import pytest

from automarshal.engine.flag_engine import (
    FlagEngine,
    WHITE_THRESHOLD,
    YELLOW_THRESHOLD,
    SLOW_SPEED_KMH,
)
from automarshal.engine.session_state import SessionState
from automarshal.models.car import CarTelemetry
from automarshal.models.flag import FlagState


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


def _make_engine(num_sectors: int = 3):
    state = SessionState(num_sectors=num_sectors)
    on_light = AsyncMock()
    on_radio_drivers = AsyncMock()
    on_radio_rc = AsyncMock()
    engine = FlagEngine(
        state=state,
        on_light=on_light,
        on_radio_drivers=on_radio_drivers,
        on_radio_rc=on_radio_rc,
    )
    return engine, state, on_light, on_radio_drivers, on_radio_rc


def _car(sector_id: int = 0, velocity_kmh: float = 120.0, car_class: str = "GT3",
         current_sector_time: float = 30.0, gap: Optional[float] = None) -> CarTelemetry:
    return CarTelemetry(
        car_id="1",
        car_class=car_class,
        sector_id=sector_id,
        velocity_kmh=velocity_kmh,
        current_sector_time=current_sector_time,
        gap_to_car_ahead=gap,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Sector flags – slow speed
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_slow_car_triggers_yellow():
    engine, state, on_light, *_ = _make_engine()
    car = _car(velocity_kmh=SLOW_SPEED_KMH - 1)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.YELLOW
    on_light.assert_awaited()


@pytest.mark.asyncio
async def test_fast_car_no_flag_without_best_time():
    engine, state, on_light, *_ = _make_engine()
    car = _car(velocity_kmh=150.0)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.GREEN
    on_light.assert_not_awaited()


# ──────────────────────────────────────────────────────────────────────────────
# Sector flags – sector time thresholds
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_white_flag_on_slow_sector_time():
    engine, state, *_ = _make_engine()
    best = 20.0
    await state.update_sector_best_time(0, "GT3", best)
    # Just over WHITE threshold, below YELLOW
    slow_time = best * (WHITE_THRESHOLD + 0.05)
    car = _car(velocity_kmh=120.0, current_sector_time=slow_time)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.WHITE


@pytest.mark.asyncio
async def test_yellow_flag_on_very_slow_sector_time():
    engine, state, *_ = _make_engine()
    best = 20.0
    await state.update_sector_best_time(0, "GT3", best)
    slow_time = best * (YELLOW_THRESHOLD + 0.1)
    car = _car(velocity_kmh=120.0, current_sector_time=slow_time)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.YELLOW


# ──────────────────────────────────────────────────────────────────────────────
# Blue flag
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_blue_flag_small_gap():
    engine, state, *_ = _make_engine()
    # Gap < BLUE_FLAG_GAP_S triggers blue flag
    car = _car(velocity_kmh=120.0, gap=1.5)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.BLUE


@pytest.mark.asyncio
async def test_no_blue_flag_large_gap():
    engine, state, *_ = _make_engine()
    car = _car(velocity_kmh=120.0, gap=5.0)
    await engine.process(car)
    flag = await state.get_sector_flag(0)
    assert flag == FlagState.GREEN


# ──────────────────────────────────────────────────────────────────────────────
# Global flags
# ──────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_red_flag_global_override():
    engine, state, on_light, on_radio_drivers, _ = _make_engine()
    await engine.trigger_red_flag()
    global_flag = await state.get_global_flag()
    assert global_flag == FlagState.RED
    on_radio_drivers.assert_awaited_once()
    call_args = on_radio_drivers.await_args[0][0]
    assert "RED FLAG" in call_args


@pytest.mark.asyncio
async def test_red_flag_blocks_sector_automation():
    engine, state, on_light, *_ = _make_engine()
    await engine.trigger_red_flag()
    on_light.reset_mock()
    # Slow car should NOT trigger sector flag change while RED is active
    car = _car(velocity_kmh=5.0)
    await engine.process(car)
    on_light.assert_not_awaited()


@pytest.mark.asyncio
async def test_safety_car_global_flag():
    engine, state, *_ = _make_engine()
    await engine.trigger_safety_car()
    global_flag = await state.get_global_flag()
    assert global_flag == FlagState.SAFETY_CAR


@pytest.mark.asyncio
async def test_green_restart_clears_global_flag():
    engine, state, *_ = _make_engine()
    await engine.trigger_safety_car()
    await engine.trigger_green_restart()
    global_flag = await state.get_global_flag()
    assert global_flag is None


@pytest.mark.asyncio
async def test_chequered_flag():
    engine, state, on_light, on_radio_drivers, _ = _make_engine()
    await engine.trigger_chequered(leader_id="7")
    global_flag = await state.get_global_flag()
    assert global_flag == FlagState.CHEQUERED
    on_radio_drivers.assert_awaited_once()
    call_args = on_radio_drivers.await_args[0][0]
    assert "7" in call_args
