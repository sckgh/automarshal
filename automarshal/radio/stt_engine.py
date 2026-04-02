"""Speech-to-text engine stub.

In production this can be backed by:
- ``speech_recognition`` with Google, Sphinx, or Whisper
- A local Whisper model for offline recognition
- Any REST STT API

Replace the ``listen`` implementation with a real STT backend.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

# Default simulated response; override in tests or real implementation.
_SIMULATED_RESPONSE = "Go ahead Sector 1"


class STTEngine:
    """Asynchronous speech-to-text interface.

    The default implementation logs and returns a pre-configured response
    string.  Replace :meth:`listen` with a real STT backend.

    Parameters:
        simulated_response: Text to return when running in stub mode.
        listen_timeout_s: How long (seconds) the stub waits before returning.
    """

    def __init__(
        self,
        simulated_response: str = _SIMULATED_RESPONSE,
        listen_timeout_s: float = 1.0,
    ) -> None:
        self._response = simulated_response
        self._timeout = listen_timeout_s

    async def listen(self) -> str:
        """Listen on the microphone and return the recognised text (stub).

        Returns:
            Recognised text string (lower-cased by convention).
        """
        logger.debug("[STT] Listening for %.1fs…", self._timeout)
        await asyncio.sleep(self._timeout)
        logger.info("[STT] Recognised: %r", self._response)
        return self._response

    def set_response(self, response: str) -> None:
        """Override the simulated STT response (useful in tests)."""
        self._response = response
