"""AutoMarshal – main asynchronous application loop.

Wires together:
  - Ingestion (MyLaps + GPS)
  - Session state (in-memory)
  - Flag engine (built-in sector rules + YAML ruleset)
  - Radio controller (RC handshake + Driver priority queue)
  - Hardware output (DMX or MQTT + GPIO PTT)
  - Heartbeat failsafe monitor

Usage::

    python -m automarshal.main
    # or
    automarshal  # if installed via pip
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Optional

from automarshal.engine.flag_engine import FlagEngine
from automarshal.engine.rule_parser import RuleParser
from automarshal.engine.session_state import SessionState, SessionMode
from automarshal.hardware.dmx_controller import DMXController
from automarshal.hardware.gpio_controller import GPIOController
from automarshal.ingestion.gps_client import GPSClient
from automarshal.ingestion.mylaps_client import MyLapsClient
from automarshal.models.car import CarTelemetry
from automarshal.models.flag import FlagState
from automarshal.radio.radio_controller import RadioController
from automarshal.radio.stt_engine import STTEngine
from automarshal.radio.tts_engine import TTSEngine
from automarshal.safety.heartbeat import HeartbeatMonitor

logger = logging.getLogger(__name__)

DEFAULT_RULES_PATH = Path(__file__).parent.parent / "rules" / "rules.yaml"
DEFAULT_NUM_SECTORS = 3


# ──────────────────────────────────────────────────────────────────────────────
# Application class
# ──────────────────────────────────────────────────────────────────────────────


class AutoMarshalApp:
    """Top-level application that owns all sub-systems.

    Parameters:
        rules_path: Path to the YAML rules file.
        num_sectors: Number of track sectors.
        mode: Session mode (Practice / Qualifying / Race).
        use_dmx: Use DMX-512 for light output (else MQTT stub is used).
        mylaps_host: Hostname of the Orbits / X2 SDK server.
        gps_host: Hostname of the X2 Link GPS server.
    """

    def __init__(
        self,
        rules_path: Path = DEFAULT_RULES_PATH,
        num_sectors: int = DEFAULT_NUM_SECTORS,
        mode: str = SessionMode.PRACTICE,
        use_dmx: bool = True,
        mylaps_host: str = "localhost",
        gps_host: str = "localhost",
    ) -> None:
        # ── State ─────────────────────────────────────────────────────────────
        self.state = SessionState(num_sectors=num_sectors, mode=mode)

        # ── Rule parser ───────────────────────────────────────────────────────
        self.rule_parser: Optional[RuleParser] = None
        if rules_path.exists():
            self.rule_parser = RuleParser(rules_path)
            self.rule_parser.load()
        else:
            logger.warning("Rules file not found: %s – running without YAML rules.", rules_path)

        # ── Hardware ──────────────────────────────────────────────────────────
        self._gpio = GPIOController()
        self._gpio.setup()
        self._dmx = DMXController() if use_dmx else None

        # ── Radio ─────────────────────────────────────────────────────────────
        tts = TTSEngine()
        stt = STTEngine()
        self.radio = RadioController(
            tts=tts,
            stt=stt,
            ptt_rc=self._gpio.ptt_rc,
            ptt_drivers=self._gpio.ptt_drivers,
        )

        # ── Flag engine ───────────────────────────────────────────────────────
        self.flag_engine = FlagEngine(
            state=self.state,
            rule_parser=self.rule_parser,
            on_light=self._on_light,
            on_radio_drivers=self._on_radio_drivers,
            on_radio_rc=self._on_radio_rc,
        )

        # ── Ingestion ─────────────────────────────────────────────────────────
        self._mylaps = MyLapsClient(
            host=mylaps_host,
            on_telemetry=self._on_telemetry,
            num_sectors=num_sectors,
        )
        self._gps = GPSClient(host=gps_host)

        # ── Failsafe ──────────────────────────────────────────────────────────
        self._heartbeat = HeartbeatMonitor(
            state=self.state,
            timeout_ms=500,
            on_failsafe=self._on_failsafe,
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Start all sub-systems and run until cancelled."""
        logger.info("AutoMarshal starting…")

        if self._dmx:
            await self._dmx.connect()

        await self.radio.start()
        await self._heartbeat.start()
        await self._gps.connect()
        await self._mylaps.connect()

        logger.info("AutoMarshal running. Press Ctrl-C to stop.")
        try:
            # Run indefinitely; the ingestion tasks drive the main loop
            while True:
                await asyncio.sleep(1)
        finally:
            await self._shutdown()

    async def _shutdown(self) -> None:
        """Gracefully stop all sub-systems."""
        logger.info("AutoMarshal shutting down…")
        await self._mylaps.disconnect()
        await self._gps.disconnect()
        await self._heartbeat.stop()
        await self.radio.stop()
        if self._dmx:
            await self._dmx.disconnect()
        self._gpio.cleanup()

    # ── Telemetry callback ────────────────────────────────────────────────────

    async def _on_telemetry(self, car: CarTelemetry) -> None:
        """Invoked by the ingestion layer for each new telemetry frame."""
        await self.state.update_car(car)
        # Update best sector time when a car completes a sector
        if car.last_sector_time > 0:
            await self.state.update_sector_best_time(
                car.sector_id, car.car_class, car.last_sector_time
            )
        await self.flag_engine.process(car)

    # ── Hardware callbacks ────────────────────────────────────────────────────

    async def _on_light(self, light_id: str, flag: FlagState) -> None:
        """Route light commands to the configured output hardware."""
        if self._dmx:
            await self._dmx.set_flag(light_id, flag)
        else:
            logger.info("Light: %s → %s", light_id, flag.value)

    async def _on_radio_drivers(self, message: str) -> None:
        """Determine the flag priority of a message and enqueue it."""
        # Infer priority flag from message content
        flag = _message_to_flag(message)
        await self.radio.driver_broadcast(message, flag)

    async def _on_radio_rc(self, sector_id: int, message: str) -> None:
        """Initiate the RC handshake for an incident report."""
        await self.radio.rc_incident(sector_id, message)

    async def _on_failsafe(self, active: bool) -> None:
        """React to failsafe state transitions."""
        if active:
            logger.critical("FAILSAFE ACTIVE – all panels set to MANUAL ONLY")
        else:
            logger.warning("Failsafe cleared – resuming automatic operation")

    # ── Voice-triggered global commands ──────────────────────────────────────

    async def command_red_flag(self) -> None:
        """Trigger an immediate red flag (e.g. from voice command)."""
        await self.flag_engine.trigger_red_flag()

    async def command_safety_car(self) -> None:
        """Deploy the safety car."""
        await self.flag_engine.trigger_safety_car()
        await self.radio.start_safety_car_loop()

    async def command_safety_car_lights_out(self) -> None:
        """Safety car lights out – leader maintains speed."""
        msg = (
            "Lights out on the safety car. "
            "Leader maintain speed. No overtaking ahead of the control line."
        )
        await self.radio.driver_broadcast(msg, FlagState.SAFETY_CAR)

    async def command_green_restart(self) -> None:
        """Green flag restart after safety car."""
        await self.radio.stop_safety_car_loop()
        await self.flag_engine.trigger_green_restart()

    async def command_chequered(self, leader_id: str = "") -> None:
        """Wave the chequered flag."""
        await self.flag_engine.trigger_chequered(leader_id)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _message_to_flag(message: str) -> FlagState:
    """Infer the flag state from a broadcast message string."""
    lower = message.lower()
    if "red flag" in lower:
        return FlagState.RED
    if "safety car" in lower:
        return FlagState.SAFETY_CAR
    if "caution" in lower or "yellow" in lower or "slowly" in lower or "stopped" in lower:
        return FlagState.YELLOW
    if "white" in lower:
        return FlagState.WHITE
    return FlagState.YELLOW  # default to caution


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

def entrypoint() -> None:
    """CLI entry point (registered in pyproject.toml)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    )

    app = AutoMarshalApp()

    loop = asyncio.get_event_loop()

    def _handle_signal() -> None:
        logger.info("Signal received; shutting down…")
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    try:
        loop.run_until_complete(app.run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        loop.close()
    sys.exit(0)


if __name__ == "__main__":
    entrypoint()
