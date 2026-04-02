"""GPIO-based PTT (Push-To-Talk) relay controller stub.

In production this uses ``RPi.GPIO`` or ``gpiozero`` on a Raspberry Pi to
toggle a relay that keys a radio transceiver.

Two relays are required:
  - ``ptt_rc_pin``: PTT relay for Channel A (Race Control).
  - ``ptt_drivers_pin``: PTT relay for Channel B (Drivers).

The stub logs PTT state changes; replace with real GPIO calls.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Default BCM GPIO pin numbers (Raspberry Pi)
DEFAULT_PTT_RC_PIN = 17
DEFAULT_PTT_DRIVERS_PIN = 27


class GPIOController:
    """Control PTT relays via GPIO.

    Parameters:
        ptt_rc_pin: BCM GPIO pin for the Race Control PTT relay.
        ptt_drivers_pin: BCM GPIO pin for the Drivers PTT relay.
    """

    def __init__(
        self,
        ptt_rc_pin: int = DEFAULT_PTT_RC_PIN,
        ptt_drivers_pin: int = DEFAULT_PTT_DRIVERS_PIN,
    ) -> None:
        self._rc_pin = ptt_rc_pin
        self._drivers_pin = ptt_drivers_pin

    def setup(self) -> None:
        """Initialise GPIO (stub).

        Real implementation::

            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self._rc_pin, GPIO.OUT, initial=GPIO.LOW)
            GPIO.setup(self._drivers_pin, GPIO.OUT, initial=GPIO.LOW)
        """
        logger.info(
            "GPIOController: setup pins RC=%d DRIVERS=%d (stub)",
            self._rc_pin, self._drivers_pin,
        )

    def cleanup(self) -> None:
        """Release GPIO resources (stub).

        Real implementation::

            import RPi.GPIO as GPIO
            GPIO.cleanup()
        """
        logger.info("GPIOController: cleanup (stub)")

    async def ptt_rc(self, active: bool) -> None:
        """Key/un-key the Race Control PTT relay.

        Args:
            active: True to assert PTT (transmit), False to release.
        """
        state = "HIGH" if active else "LOW"
        logger.debug("GPIOController: RC PTT pin %d → %s", self._rc_pin, state)
        await asyncio.sleep(0)  # yield; replace with GPIO.output(self._rc_pin, active)

    async def ptt_drivers(self, active: bool) -> None:
        """Key/un-key the Drivers PTT relay.

        Args:
            active: True to assert PTT (transmit), False to release.
        """
        state = "HIGH" if active else "LOW"
        logger.debug("GPIOController: Drivers PTT pin %d → %s", self._drivers_pin, state)
        await asyncio.sleep(0)  # yield; replace with GPIO.output(self._drivers_pin, active)
