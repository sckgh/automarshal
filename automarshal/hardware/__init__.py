"""Hardware sub-package: DMX, MQTT, and GPIO interface stubs."""

from automarshal.hardware.dmx_controller import DMXController
from automarshal.hardware.mqtt_controller import MQTTController
from automarshal.hardware.gpio_controller import GPIOController

__all__ = ["DMXController", "MQTTController", "GPIOController"]
