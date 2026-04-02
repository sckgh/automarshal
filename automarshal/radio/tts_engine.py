"""Text-to-speech engine stub.

In production this can be backed by:
- ``edge-tts`` (Microsoft Azure neural TTS, no API key required)
- pyttsx3 (offline)
- Any REST TTS API

Replace the ``speak`` implementation to integrate the real TTS backend.
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


class TTSEngine:
    """Asynchronous text-to-speech interface.

    The default implementation logs the message and simulates audio playback
    latency.  Replace :meth:`speak` with a real TTS backend.

    Parameters:
        speaking_rate_wps: Approximate word-per-second rate used to estimate
            simulated playback duration.
    """

    def __init__(self, speaking_rate_wps: float = 2.5, min_duration_s: float = 0.5) -> None:
        self._rate = speaking_rate_wps
        self._min_duration = min_duration_s

    async def speak(self, text: str) -> None:
        """Synthesise and play *text* (stub: logs and sleeps).

        Args:
            text: The message to speak.
        """
        word_count = len(text.split())
        duration = max(self._min_duration, word_count / self._rate)
        logger.info("[TTS] Speaking (%.1fs): %r", duration, text)
        await asyncio.sleep(duration)
