"""ElevenLabs TTS — платний, найякісніший голос. API-контракт (endpoint/заголовки/тіло
запиту) узятий з офіційного Remotion voiceover skill (.claude/commands/Remotion Rule-
Voiceover.md) — той самий виклик, лише через Python `requests` замість TS `fetch`.
"""

import os
from pathlib import Path

import requests

from ..base import ProviderConfigError, TTSProvider
from ._audio_utils import mp3_duration_ms

_API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
# Голос, обраний користувачем (elevenlabs.io/voices/iB0m5bo5Htdz0t9yE0xq) — перевірено (200 на
# синтез). Rachel (стандартний демо-голос) звучить штучно — не використовуємо як дефолт.
# Див. app/providers/tts/voices.py для повного каталогу.
_DEFAULT_VOICE_ID = "iB0m5bo5Htdz0t9yE0xq"


class ElevenLabsTTSProvider(TTSProvider):
    file_extension = "mp3"

    def __init__(self) -> None:
        api_key = os.environ.get("ELEVENLABS_API_KEY")
        if not api_key:
            raise ProviderConfigError(
                "ELEVENLABS_API_KEY не знайдено. Візьми ключ на https://elevenlabs.io "
                "(Profile -> API Keys) і додай у .env (див. .env.example)."
            )
        self._api_key = api_key
        self._default_voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or _DEFAULT_VOICE_ID

    def resolve_voice(self, language: str, voice: str | None = None) -> str:
        # eleven_multilingual_v2 говорить усіма нашими мовами тим самим голосом за
        # замовчуванням — ELEVENLABS_VOICE_ID_<LANG> у .env потрібен лише для "рідного"
        # голосу конкретної мови; голос, обраний у UI, перекриває і його.
        return voice or os.environ.get(f"ELEVENLABS_VOICE_ID_{language.upper()}") or self._default_voice_id

    def synthesize(
        self,
        text: str,
        out_path: Path,
        language: str,
        voice: str | None = None,
        previous_text: str | None = None,
        next_text: str | None = None,
    ) -> int:
        voice_id = self.resolve_voice(language, voice)
        body = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "style": 0.3},
        }
        # Сусідні репліки — контекст для інтонації: окремо озвучені сегменти звучать як одне читання.
        if previous_text:
            body["previous_text"] = previous_text[-400:]
        if next_text:
            body["next_text"] = next_text[:400]
        response = requests.post(
            _API_URL.format(voice_id=voice_id),
            headers={
                "xi-api-key": self._api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json=body,
            timeout=120,
        )
        if response.status_code != 200:
            raise ProviderConfigError(
                f"ElevenLabs API помилка {response.status_code}: {response.text[:300]}"
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(response.content)
        return mp3_duration_ms(out_path)
