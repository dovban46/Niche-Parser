"""Спільна утиліта для TTS-провайдерів, що віддають MP3 (ElevenLabs, edge-tts).

Тривалість — через ffprobe (враховує gapless-інфо, тож збігається зі склеєною озвучкою); якщо ffmpeg
немає — читаємо MP3-фрейми через `mutagen` (трохи завищує, але без залежності від ffmpeg).
"""

from pathlib import Path

from mutagen.mp3 import MP3

from ...ffutil import probe_duration


def mp3_duration_ms(path: Path) -> int:
    seconds = probe_duration(path)
    if seconds is None:
        seconds = MP3(str(path)).info.length
    return int(seconds * 1000)
