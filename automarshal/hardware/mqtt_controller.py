"""MQTT-based light panel controller stub.

Some track panel systems use MQTT for command distribution rather than DMX.
This controller publishes flag-change messages to a topic per panel.

Topic format: ``automarshal/lights/{light_id}``
Payload: JSON ``{"flag": "YELLOW", "rgb": [255, 200, 0]}``
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from automarshal.models.flag import FlagState

logger = logging.getLogger(__name__)

_FLAG_COLOURS: dict[FlagState, list[int]] = {
    FlagState.GREEN: [0, 255, 0],
    FlagState.WHITE: [255, 255, 255],
    FlagState.YELLOW: [255, 200, 0],
    FlagState.BLUE: [0, 0, 255],
    FlagState.RED: [255, 0, 0],
    FlagState.SAFETY_CAR: [255, 140, 0],
    FlagState.CHEQUERED: [255, 255, 255],
    FlagState.MANUAL_ONLY: [0, 0, 0],
}

TOPIC_PREFIX = "automarshal/lights/"


class MQTTController:
    """Publish flag-change commands to MQTT-connected light panels.

    Parameters:
        broker: MQTT broker hostname or IP.
        port: MQTT broker port (default 1883).
        topic_prefix: Topic prefix for light commands.
    """

    def __init__(
        self,
        broker: str = "localhost",
        port: int = 1883,
        topic_prefix: str = TOPIC_PREFIX,
    ) -> None:
        self.broker = broker
        self.port = port
        self._prefix = topic_prefix
        self._client = None  # aiomqtt.Client instance set on connect

    async def connect(self) -> None:
        """Connect to the MQTT broker (stub)."""
        logger.info("MQTTController: connecting to %s:%d (stub)", self.broker, self.port)
        # Real implementation:
        #   import aiomqtt
        #   self._client = aiomqtt.Client(hostname=self.broker, port=self.port)
        #   await self._client.__aenter__()

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker."""
        logger.info("MQTTController: disconnected (stub)")

    async def set_flag(self, light_id: str, flag: FlagState) -> None:
        """Publish a flag-change command for *light_id*.

        Args:
            light_id: Panel identifier (e.g. ``"Sector_1"``).
            flag: The flag state to display.
        """
        topic = f"{self._prefix}{light_id}"
        payload = json.dumps({"flag": flag.value, "rgb": _FLAG_COLOURS.get(flag, [0, 0, 0])})
        logger.info("MQTTController: publish %s → %s (stub)", topic, payload)
        # Real implementation:
        #   await self._client.publish(topic, payload)
