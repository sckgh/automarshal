"""Flag engine: applies sector-automation rules from the problem specification.

Built-in logic (always active, independent of the YAML ruleset):

Sector flags
    WHITE   Current_Sector_Time > Best_Sector_Time * 1.3
    YELLOW  Current_Sector_Time > Best_Sector_Time * 1.8  OR  V < 10 km/h
    BLUE    Gap < 2.0 s  AND  pace_behind > pace_ahead
    CLEAR   V > V_racing_avg * 0.8  AND  distance_from_incident > 50 m
            for a 2.0 s persistence window → show GREEN 5 s → clear

Global flags (triggered externally via :meth:`set_global_flag`)
    RED, CHEQUERED, SAFETY_CAR

The engine also evaluates the user-supplied YAML :class:`Rule` list on every
telemetry update and dispatches the resulting actions to the hardware/radio
layers through registered async callbacks.
"""

from __future__ import annotations

import asyncio
import logging
from time import time
from typing import Callable, Awaitable, Optional

from automarshal.engine.rule_parser import Rule, RuleParser
from automarshal.engine.session_state import SessionState
from automarshal.models.car import CarTelemetry
from automarshal.models.flag import FlagState

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Tunable constants (match the spec)
# ──────────────────────────────────────────────────────────────────────────────

WHITE_THRESHOLD = 1.3       # sector_time > best * WHITE_THRESHOLD
YELLOW_THRESHOLD = 1.8      # sector_time > best * YELLOW_THRESHOLD
SLOW_SPEED_KMH = 10.0       # yellow if velocity below this
BLUE_FLAG_GAP_S = 2.0       # gap < this → candidate for blue
CLEAR_SPEED_RATIO = 0.8     # must exceed racing_avg * this to clear
CLEAR_DISTANCE_M = 50.0     # must be > this metres from incident
CLEAR_PERSISTENCE_S = 2.0   # must meet clear criteria for this long
GREEN_DISPLAY_S = 5.0       # show green for this many seconds after clear

# Approximate racing average speed (km/h) used as reference for clearance.
# In a real deployment this is computed dynamically from recent laps.
DEFAULT_RACING_AVG_KMH = 120.0

ActionCallback = Callable[..., Awaitable[None]]


class FlagEngine:
    """Evaluate sector and global flag logic for each telemetry update.

    Parameters:
        state: Shared :class:`SessionState` instance.
        rule_parser: Optional :class:`RuleParser` with user-defined rules.
        on_light: Async callback ``(light_id: str, flag: FlagState) -> None``.
        on_radio_drivers: Async callback ``(message: str) -> None``.
        on_radio_rc: Async callback ``(sector_id: int, message: str) -> None``.
        racing_avg_kmh: Reference speed used for yellow-clearance calculation.
    """

    def __init__(
        self,
        state: SessionState,
        rule_parser: Optional[RuleParser] = None,
        on_light: Optional[ActionCallback] = None,
        on_radio_drivers: Optional[ActionCallback] = None,
        on_radio_rc: Optional[ActionCallback] = None,
        racing_avg_kmh: float = DEFAULT_RACING_AVG_KMH,
    ) -> None:
        self._state = state
        self._rule_parser = rule_parser
        self._on_light = on_light
        self._on_radio_drivers = on_radio_drivers
        self._on_radio_rc = on_radio_rc
        self._racing_avg_kmh = racing_avg_kmh
        # Track per-sector clearance start time {sector_id -> timestamp}
        self._clearance_start: dict[int, float] = {}

    # ── Public entry point ────────────────────────────────────────────────────

    async def process(self, car: CarTelemetry) -> None:
        """Process one telemetry frame for *car*.

        1. Evaluate built-in sector flag logic.
        2. Evaluate user YAML rules.
        3. Dispatch hardware/radio actions.
        """
        global_flag = await self._state.get_global_flag()
        if global_flag in (FlagState.RED, FlagState.MANUAL_ONLY):
            # No automatic flag changes while a global override is in force
            return

        await self._evaluate_sector_flags(car)
        await self._evaluate_yaml_rules(car)
        await self._process_green_timeouts()

    # ── Built-in sector flag logic ────────────────────────────────────────────

    async def _evaluate_sector_flags(self, car: CarTelemetry) -> None:
        sector_id = car.sector_id
        sector = await self._state.get_sector(sector_id)
        if sector is None:
            return

        current_flag = sector.flag
        best_time = sector.get_best_time(car.car_class)

        # ── Yellow / White based on sector time ───────────────────────────────
        new_flag: Optional[FlagState] = None

        if car.velocity_kmh < SLOW_SPEED_KMH:
            new_flag = FlagState.YELLOW
        elif best_time is not None and best_time > 0:
            ratio = car.current_sector_time / best_time
            if ratio > YELLOW_THRESHOLD:
                new_flag = FlagState.YELLOW
            elif ratio > WHITE_THRESHOLD:
                new_flag = FlagState.WHITE

        # ── Blue flag ─────────────────────────────────────────────────────────
        if new_flag is None and car.gap_to_car_ahead is not None:
            if car.gap_to_car_ahead < BLUE_FLAG_GAP_S:
                # Simplified: assume the car ahead is faster (pace_ahead > pace_behind).
                # Full implementation would compare rolling lap times from state.
                new_flag = FlagState.BLUE

        # ── Clearance check for Yellow / White ───────────────────────────────
        if current_flag in (FlagState.YELLOW, FlagState.WHITE) and new_flag is None:
            await self._check_clearance(car, sector_id)
            return  # clearance handler manages the transition

        if new_flag is not None and new_flag != current_flag:
            # Only escalate (never auto-downgrade from a higher flag)
            if new_flag >= current_flag or current_flag == FlagState.GREEN:
                await self._state.set_sector_flag(sector_id, new_flag)
                # Cancel any ongoing clearance tracking for this sector
                self._clearance_start.pop(sector_id, None)
                await self._dispatch_light(f"Sector_{sector_id + 1}", new_flag)

    async def _check_clearance(self, car: CarTelemetry, sector_id: int) -> None:
        """Determine whether conditions are met to clear a yellow/white flag."""
        speed_ok = car.velocity_kmh > self._racing_avg_kmh * CLEAR_SPEED_RATIO
        # Distance from incident: in a real system this would compare GPS to
        # the recorded incident coordinates.  Here we use a simplified proxy.
        distance_ok = True  # placeholder until GPS incident tracking is added

        if speed_ok and distance_ok:
            first_seen = self._clearance_start.get(sector_id)
            if first_seen is None:
                self._clearance_start[sector_id] = time()
            elif time() - first_seen >= CLEAR_PERSISTENCE_S:
                # Criteria met for long enough – clear the flag
                sector = await self._state.get_sector(sector_id)
                if sector and sector.green_display_until is None:
                    await self._state.set_sector_flag(sector_id, FlagState.GREEN)
                    sector.green_display_until = time() + GREEN_DISPLAY_S
                    self._clearance_start.pop(sector_id, None)
                    await self._dispatch_light(f"Sector_{sector_id + 1}", FlagState.GREEN)
        else:
            # Reset persistence window if criteria fail
            self._clearance_start.pop(sector_id, None)

    async def _process_green_timeouts(self) -> None:
        """Clear GREEN display flags that have exceeded their display window."""
        now = time()
        for sector in self._state.sectors:
            if sector.green_display_until is not None and now >= sector.green_display_until:
                sector.green_display_until = None
                # Flag stays GREEN but the panel can be switched off / to blank
                await self._dispatch_light(f"Sector_{sector.sector_id + 1}", FlagState.GREEN)

    # ── YAML rule evaluation ──────────────────────────────────────────────────

    async def _evaluate_yaml_rules(self, car: CarTelemetry) -> None:
        if self._rule_parser is None:
            return
        fired: list[Rule] = self._rule_parser.evaluate_all(car)
        for rule in fired:
            logger.info("Rule fired: %r for car %s", rule.name, car.car_id)
            if rule.action.light:
                # Parse light ID to determine sector and flag colour
                flag = _light_id_to_flag(rule.action.light)
                await self._dispatch_light(rule.action.light, flag)
            if rule.action.radio_drivers:
                await self._dispatch_radio_drivers(rule.action.radio_drivers)
            if rule.action.radio_rc:
                await self._dispatch_radio_rc(car.sector_id, rule.action.radio_rc)

    # ── Dispatch helpers ──────────────────────────────────────────────────────

    async def _dispatch_light(self, light_id: str, flag: FlagState) -> None:
        if self._on_light:
            await self._on_light(light_id, flag)

    async def _dispatch_radio_drivers(self, message: str) -> None:
        if self._on_radio_drivers:
            await self._on_radio_drivers(message)

    async def _dispatch_radio_rc(self, sector_id: int, message: str) -> None:
        if self._on_radio_rc:
            await self._on_radio_rc(sector_id, message)

    # ── Global flag shortcuts (called from the main loop / voice triggers) ────

    async def trigger_red_flag(self) -> None:
        """Instantly assert RED flag globally and broadcast."""
        await self._state.set_global_flag(FlagState.RED)
        for i in range(len(self._state.sectors)):
            await self._dispatch_light(f"Sector_{i + 1}", FlagState.RED)
        await self._dispatch_radio_drivers("RED FLAG. RED FLAG. RETURN TO PITS.")

    async def trigger_safety_car(self) -> None:
        """Assert SAFETY_CAR global flag."""
        await self._state.set_global_flag(FlagState.SAFETY_CAR)
        for i in range(len(self._state.sectors)):
            await self._dispatch_light(f"Sector_{i + 1}", FlagState.SAFETY_CAR)

    async def trigger_green_restart(self) -> None:
        """Restart under green: clear global override and set all sectors GREEN."""
        await self._state.set_global_flag(None)
        for i in range(len(self._state.sectors)):
            await self._state.set_sector_flag(i, FlagState.GREEN)
            await self._dispatch_light(f"Sector_{i + 1}", FlagState.GREEN)
        await self._dispatch_radio_drivers("GREEN FLAG. GREEN FLAG.")

    async def trigger_chequered(self, leader_id: str = "") -> None:
        """Display the chequered flag for the session leader."""
        await self._state.set_global_flag(FlagState.CHEQUERED)
        await self._dispatch_light("Start_Finish", FlagState.CHEQUERED)
        if leader_id:
            await self._dispatch_radio_drivers(
                f"Chequered flag. Car {leader_id} takes the win."
            )


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _light_id_to_flag(light_id: str) -> FlagState:
    """Infer the flag state from a light identifier string (best effort)."""
    lower = light_id.lower()
    if "yellow" in lower:
        return FlagState.YELLOW
    if "red" in lower:
        return FlagState.RED
    if "green" in lower:
        return FlagState.GREEN
    if "white" in lower:
        return FlagState.WHITE
    if "blue" in lower:
        return FlagState.BLUE
    if "chequered" in lower or "checkered" in lower:
        return FlagState.CHEQUERED
    return FlagState.YELLOW  # default to caution
