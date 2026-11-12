"""Озвучка explainer-а через ElevenLabs /with-timestamps: повертає mp3 + таймінги кожного символу, з яких виходять
межі бітів, слів для субтитрів і гучність для рота. Один запит на весь текст = цільна інтонація."""

import base64
import os
from pathlib import Path

import requests

from .. import config  # noqa: F401  (підвантажує .env)
from ..providers.base import ProviderConfigError

# George — «warm, captivating storyteller» (premade); для мудреця-оповідача. Перевизначається EXPLAINER_VOICE_ID.
DEFAULT_VOICE = "JBFqnCBsd6RMkjVDRZzb"
_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"


def synthesize_with_timestamps(text: str, out_mp3: Path, voice_id: str | None = None,
                               stability: float = 0.38, style: float = 0.45,
                               previous_text: str = "", next_text: str = "") -> dict:
    """Пише mp3, повертає {"chars": [...], "starts": [...], "ends": [...], "chars_billed": N}."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        raise ProviderConfigError("ELEVENLABS_API_KEY не знайдено в .env")
    voice = voice_id or os.environ.get("EXPLAINER_VOICE_ID") or DEFAULT_VOICE
    body = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": stability, "similarity_boost": 0.75, "style": style, "use_speaker_boost": True},
    }
    if previous_text:
        body["previous_text"] = previous_text[-500:]
    if next_text:
        body["next_text"] = next_text[:500]
    r = requests.post(
        _URL.format(voice=voice),
        params={"output_format": "mp3_44100_128"},
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json=body,
        timeout=300,
    )
    if r.status_code != 200:
        raise ProviderConfigError(f"ElevenLabs with-timestamps помилка {r.status_code}: {r.text[:300]}")
    data = r.json()
    out_mp3.write_bytes(base64.b64decode(data["audio_base64"]))
    al = data.get("alignment") or data.get("normalized_alignment")
    return {"chars": al["characters"], "starts": al["character_start_times_seconds"],
            "ends": al["character_end_times_seconds"], "chars_billed": len(text)}


def words_from_alignment(al: dict) -> list[dict]:
    """[{w, s, e, i0, i1}] — слова з символьними межами (i0..i1 в оригінальному тексті)."""
    words, cur, s, i0 = [], "", None, 0
    for idx, (ch, st, en) in enumerate(zip(al["chars"], al["starts"], al["ends"])):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": s, "e": prev_e, "i0": i0, "i1": idx})
                cur, s = "", None
        else:
            if not cur:
                s, i0 = st, idx
            cur += ch
            prev_e = en
    if cur:
        words.append({"w": cur, "s": s, "e": prev_e, "i0": i0, "i1": len(al["chars"])})
    return words
