"""Stub-реалізація TTSProvider — без жодного API-ключа.

Пише справжній валідний WAV-файл (тиша) тривалістю, розрахованою з кількості слів
(config.WORDS_PER_MINUTE) — так, щоб tts_synthesize/video_assemble мали реальні
файли з реальною тривалістю для роботи решти пайплайна. Замінюється на
providers/tts/google_provider.py в наступному кроці.
"""

import struct
import wave
from pathlib import Path

from ...config import WORDS_PER_MINUTE
from ..base import TTSProvider

_SAMPLE_RATE = 16_000
_MIN_DURATION_MS = 800


class StubTTSProvider(TTSProvider):
    def resolve_voice(self, language: str, voice: str | None = None) -> str:
        return "stub"

    def synthesize(
        self,
        text: str,
        out_path: Path,
        language: str,
        voice: str | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> int:
        word_count = max(len(text.split()), 1)
        duration_ms = max(int(word_count / WORDS_PER_MINUTE * 60_000), _MIN_DURATION_MS)

        out_path.parent.mkdir(parents=True, exist_ok=True)
        n_frames = int(_SAMPLE_RATE * duration_ms / 1000)
        silence_frame = struct.pack("<h", 0)

        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(_SAMPLE_RATE)
            wav_file.writeframes(silence_frame * n_frames)

        return duration_ms
