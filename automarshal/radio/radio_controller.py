"""Dual-channel radio controller.

Channel A – Race Control (RC):
    Handshake protocol::

        System  →  "Race Control, this is Sector {X}."
        RC      →  (STT) "Go ahead Sector {X}."
        System  →  "Car {No} traveling slowly/stopped."

Channel B – Drivers:
    Priority stack (Red > SC > Yellow > White).
    Higher-priority messages interrupt ongoing lower-priority audio immediately.
    Blue flag audio is NOT broadcast on this channel.

Both channels share a single :class:`RadioController` instance.  Each channel
maintains its own asyncio queue and state machine.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from automarshal.models.flag import FlagState
from automarshal.radio.tts_engine import TTSEngine
from automarshal.radio.stt_engine import STTEngine

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

HANDSHAKE_TIMEOUT_S = 10.0   # Maximum wait for RC acknowledge
SC_LOOP_INTERVAL_S = 90.0    # Safety Car message repeat interval


class RadioChannel(str, Enum):
    """The two independent radio channels."""
    RACE_CONTROL = "RC"   # Channel A – handshake-based
    DRIVERS = "DRIVERS"   # Channel B – interrupt-driven


class HandshakeState(Enum):
    """State machine for the Race Control handshake."""
    IDLE = auto()
    CALLING = auto()        # "Race Control, this is Sector X."
    AWAITING_ACK = auto()   # Listening for "Go ahead Sector X."
    TRANSMITTING = auto()   # Sending incident detail
    COMPLETE = auto()


# ──────────────────────────────────────────────────────────────────────────────
# Driver channel message priority
# ──────────────────────────────────────────────────────────────────────────────

# Lower number = higher priority
_DRIVER_PRIORITY: dict[FlagState, int] = {
    FlagState.RED: 0,
    FlagState.SAFETY_CAR: 1,
    FlagState.YELLOW: 2,
    FlagState.WHITE: 3,
}

# Blue is not broadcast to drivers per spec
_DRIVER_BROADCAST_FLAGS = frozenset(_DRIVER_PRIORITY)


@dataclass(order=True)
class _DriverMessage:
    """A queued message for the Drivers channel, sortable by priority."""
    priority: int
    message: str = field(compare=False)
    flag: FlagState = field(compare=False, default=FlagState.YELLOW)


# ──────────────────────────────────────────────────────────────────────────────
# Radio Controller
# ──────────────────────────────────────────────────────────────────────────────


class RadioController:
    """Manage both radio channels and their respective state machines.

    Parameters:
        tts: Text-to-speech engine to play audio.
        stt: Speech-to-text engine to recognise RC responses.
        ptt_rc: Async callable to toggle PTT on the RC channel ``(active: bool)``.
        ptt_drivers: Async callable to toggle PTT on the Drivers channel.
    """

    def __init__(
        self,
        tts: Optional[TTSEngine] = None,
        stt: Optional[STTEngine] = None,
        ptt_rc=None,
        ptt_drivers=None,
    ) -> None:
        self._tts = tts or TTSEngine()
        self._stt = stt or STTEngine()
        self._ptt_rc = ptt_rc
        self._ptt_drivers = ptt_drivers

        # Channel A – Race Control
        self._rc_state: HandshakeState = HandshakeState.IDLE
        self._rc_queue: asyncio.Queue[tuple[int, str]] = asyncio.Queue()
        self._rc_task: Optional[asyncio.Task] = None

        # Channel B – Drivers (priority queue via heap)
        self._driver_queue: asyncio.PriorityQueue[_DriverMessage] = asyncio.PriorityQueue()
        self._driver_task: Optional[asyncio.Task] = None
        self._driver_current_priority: Optional[int] = None
        self._driver_interrupted = asyncio.Event()

        # Safety car loop
        self._sc_task: Optional[asyncio.Task] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the background consumer tasks for both channels."""
        self._rc_task = asyncio.create_task(self._rc_consumer(), name="rc-consumer")
        self._driver_task = asyncio.create_task(
            self._driver_consumer(), name="driver-consumer"
        )
        logger.info("RadioController started")

    async def stop(self) -> None:
        """Cancel background tasks and stop the safety-car loop."""
        for task in (self._rc_task, self._driver_task, self._sc_task):
            if task:
                task.cancel()
        logger.info("RadioController stopped")

    # ── Public dispatch API ───────────────────────────────────────────────────

    async def rc_incident(self, sector_id: int, detail: str) -> None:
        """Queue a handshake-based incident report for Race Control.

        Args:
            sector_id: Zero-based sector index where the incident occurred.
            detail: Incident detail string (e.g. "Car 7 traveling slowly").
        """
        await self._rc_queue.put((sector_id, detail))

    async def driver_broadcast(self, message: str, flag: FlagState) -> None:
        """Enqueue a priority-ordered broadcast on the Drivers channel.

        Blue flag audio is silently ignored per the spec.

        Args:
            message: Message string to broadcast.
            flag: Flag state that triggered the message (used for priority).
        """
        if flag not in _DRIVER_BROADCAST_FLAGS:
            logger.debug(
                "Driver broadcast suppressed for flag %s: %r", flag.value, message
            )
            return
        priority = _DRIVER_PRIORITY.get(flag, 99)
        item = _DriverMessage(priority=priority, message=message, flag=flag)
        await self._driver_queue.put(item)
        # Signal interrupt if this message has higher priority than current
        if (
            self._driver_current_priority is not None
            and priority < self._driver_current_priority
        ):
            self._driver_interrupted.set()

    # ── Safety Car loop ───────────────────────────────────────────────────────

    async def start_safety_car_loop(self) -> None:
        """Begin repeating "Safety Car deployed." every 90 seconds."""
        await self.stop_safety_car_loop()
        self._sc_task = asyncio.create_task(self._sc_loop(), name="sc-loop")

    async def stop_safety_car_loop(self) -> None:
        """Cancel the Safety Car repeat loop."""
        if self._sc_task:
            self._sc_task.cancel()
            try:
                await self._sc_task
            except asyncio.CancelledError:
                pass
            self._sc_task = None

    async def _sc_loop(self) -> None:
        while True:
            await self._speak_drivers("Safety Car deployed.")
            await asyncio.sleep(SC_LOOP_INTERVAL_S)

    # ── Race Control handshake consumer ──────────────────────────────────────

    async def _rc_consumer(self) -> None:
        """Process one RC incident at a time using the handshake protocol."""
        while True:
            sector_id, detail = await self._rc_queue.get()
            await self._perform_handshake(sector_id, detail)

    async def _perform_handshake(self, sector_id: int, detail: str) -> None:
        """Execute the three-step Race Control handshake."""
        sector_num = sector_id + 1
        self._rc_state = HandshakeState.CALLING

        # Step 1: Call Race Control
        call = f"Race Control, this is Sector {sector_num}."
        logger.info("[RC] %s", call)
        await self._speak_rc(call)
        self._rc_state = HandshakeState.AWAITING_ACK

        # Step 2: Listen for acknowledgement
        expected_ack = f"go ahead sector {sector_num}"
        try:
            heard = await asyncio.wait_for(
                self._stt.listen(), timeout=HANDSHAKE_TIMEOUT_S
            )
        except asyncio.TimeoutError:
            logger.warning("[RC] No acknowledgement received for Sector %d; aborting.", sector_num)
            self._rc_state = HandshakeState.IDLE
            return

        if expected_ack not in heard.lower():
            logger.warning(
                "[RC] Unexpected acknowledgement %r (expected %r); aborting.",
                heard, expected_ack,
            )
            self._rc_state = HandshakeState.IDLE
            return

        # Step 3: Transmit incident detail
        self._rc_state = HandshakeState.TRANSMITTING
        logger.info("[RC] %s", detail)
        await self._speak_rc(detail)
        self._rc_state = HandshakeState.COMPLETE
        self._rc_state = HandshakeState.IDLE

    # ── Driver channel priority consumer ─────────────────────────────────────

    async def _driver_consumer(self) -> None:
        """Continuously drain the driver priority queue, honouring interrupts."""
        while True:
            item: _DriverMessage = await self._driver_queue.get()
            self._driver_current_priority = item.priority
            self._driver_interrupted.clear()

            logger.info(
                "[DRIVERS] Broadcasting (priority %d): %r",
                item.priority, item.message,
            )
            speak_task = asyncio.create_task(self._speak_drivers(item.message))
            interrupt_task = asyncio.create_task(self._driver_interrupted.wait())

            done, pending = await asyncio.wait(
                {speak_task, interrupt_task},
                return_when=asyncio.FIRST_COMPLETED,
            )

            for t in pending:
                t.cancel()

            if interrupt_task in done:
                logger.info("[DRIVERS] Broadcast interrupted by higher-priority message.")

            self._driver_current_priority = None

    # ── Low-level PTT / TTS helpers ───────────────────────────────────────────

    async def _speak_rc(self, text: str) -> None:
        if self._ptt_rc:
            await self._ptt_rc(True)
        await self._tts.speak(text)
        if self._ptt_rc:
            await self._ptt_rc(False)

    async def _speak_drivers(self, text: str) -> None:
        if self._ptt_drivers:
            await self._ptt_drivers(True)
        await self._tts.speak(text)
        if self._ptt_drivers:
            await self._ptt_drivers(False)

    @property
    def rc_state(self) -> HandshakeState:
        """Current handshake state of the Race Control channel."""
        return self._rc_state
