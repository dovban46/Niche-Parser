"""Безкоштовний TTS без жодного API-ключа — через публічний сервіс синтезу мовлення
Microsoft Edge (пакет `edge-tts`, MIT, неофіційна, але широко використовувана й активно
підтримувана обгортка навколо Read Aloud). Гірша керованість тону за ElevenLabs, та
пристойна якість нейронних голосів і нуль вартості — гарний варіант для старту/тестів.
"""

import asyncio
import os
from pathlib import Path

import edge_tts

from ..base import TTSProvider
from ._audio_utils import mp3_duration_ms

# Один нейронний голос на мову з SUPPORTED_LANGUAGES (schemas.py). Повний список усіх
# доступних голосів edge-tts: `edge-tts --list-voices` після встановлення пакета —
# можна підмінити тут будь-який голос на смак, головне лишити той самий код мови як ключ.
_VOICE_BY_LANGUAGE = {
    "uk": "uk-UA-PolinaNeural",
    "en": "en-US-AriaNeural",
    "pl": "pl-PL-ZofiaNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "it": "it-IT-ElsaNeural",
    "fr": "fr-FR-DeniseNeural",
}
_FALLBACK_LANGUAGE = "uk"


class EdgeTTSProvider(TTSProvider):
    file_extension = "mp3"

    def resolve_voice(self, language: str, voice: str | None = None) -> str:
        if voice:
            return voice
        # EDGE_TTS_VOICE_EN=... в .env перекриє дефолт лише для конкретної мови — не треба
        # чіпати код, якщо хочеться просто інший голос для однієї мови.
        override = os.environ.get(f"EDGE_TTS_VOICE_{language.upper()}")
        if override:
            return override
        return _VOICE_BY_LANGUAGE.get(language, _VOICE_BY_LANGUAGE[_FALLBACK_LANGUAGE])

    def synthesize(
        self,
        text: str,
        out_path: Path,
        language: str,
        voice: str | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> int:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.run(_synthesize_async(text, self.resolve_voice(language, voice), out_path))
        return mp3_duration_ms(out_path)


async def _synthesize_async(text: str, voice: str, out_path: Path) -> None:
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(out_path))
