"""DMX-512 light panel controller stub.

DMX-512 is a serial communication protocol used to control stage/track lighting.
In production integrate a library such as ``pyserial``-based DMX adapter or the
Open Lighting Architecture (OLA) Python bindings.

Each track sector panel maps to a DMX universe start address.  The flag colour
maps to an RGB triplet that is sent to the panel.
"""

from __future__ import annotations

import logging
from typing import Optional

from automarshal.models.flag import FlagState

logger = logging.getLogger(__name__)

# Default DMX RGB values per flag colour
_FLAG_COLOURS: dict[FlagState, tuple[int, int, int]] = {
    FlagState.GREEN: (0, 255, 0),
    FlagState.WHITE: (255, 255, 255),
    FlagState.YELLOW: (255, 200, 0),
    FlagState.BLUE: (0, 0, 255),
    FlagState.RED: (255, 0, 0),
    FlagState.SAFETY_CAR: (255, 140, 0),   # orange
    FlagState.CHEQUERED: (255, 255, 255),   # alternate black/white handled by panel
    FlagState.MANUAL_ONLY: (0, 0, 0),       # all off
}

# Mapping from light_id string to DMX universe start channel (configurable)
_DEFAULT_CHANNEL_MAP: dict[str, int] = {
    "Sector_1": 1,
    "Sector_2": 17,
    "Sector_3": 33,
    "Sector_4": 49,
    "Start_Finish": 65,
}


class DMXController:
    """Control track flag panels over DMX-512.

    Parameters:
        port: Serial port or OLA device path (e.g. ``/dev/ttyUSB0``).
        channel_map: Mapping from light_id to DMX start channel.
    """

    def __init__(
        self,
        port: str = "/dev/ttyUSB0",
        channel_map: Optional[dict[str, int]] = None,
    ) -> None:
        self.port = port
        self._channel_map = channel_map or dict(_DEFAULT_CHANNEL_MAP)
        self._connected = False

    async def connect(self) -> None:
        """Open the DMX serial interface (stub)."""
        logger.info("DMXController: opening port %s (stub)", self.port)
        self._connected = True

    async def disconnect(self) -> None:
        """Close the DMX serial interface."""
        self._connected = False
        logger.info("DMXController: port closed")

    async def set_flag(self, light_id: str, flag: FlagState) -> None:
        """Set the colour of a light panel to represent *flag*.

        Args:
            light_id: Identifier matching an entry in the channel map
                (e.g. ``"Sector_1"``).
            flag: The flag state to display.
        """
        colour = _FLAG_COLOURS.get(flag, (0, 0, 0))
        channel = self._channel_map.get(light_id)
        if channel is None:
            logger.warning("DMXController: unknown light_id %r; ignoring.", light_id)
            return
        logger.info(
            "DMXController: light=%r flag=%s rgb=%s ch=%d (stub)",
            light_id, flag.value, colour, channel,
        )
        # TODO: write RGB to DMX universe at ``channel`` via serial adapter

    def add_channel(self, light_id: str, dmx_channel: int) -> None:
        """Register a new light panel."""
        self._channel_map[light_id] = dmx_channel
