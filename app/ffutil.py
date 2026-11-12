"""Тонка обгортка над ffmpeg/ffprobe — спільна для озвучки, збірки відео й бібліотеки ефектів."""

import shutil
import subprocess
from pathlib import Path


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def probe_duration(path: Path) -> float | None:
    """Тривалість медіафайлу в секундах. Для mp3 ffprobe враховує gapless-інфо кодека, тож
    сума тривалостей сегментів збігається з тривалістю склеєної озвучки (на відміну від
    mutagen, що завищує кожен сегмент на ~35 мс — за 170 сегментів це 6 с розсинхрону)."""
    if not shutil.which("ffprobe"):
        return None
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return float(out.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args],
        check=True,
        capture_output=True,
        cwd=str(cwd) if cwd else None,
    )


def error_tail(exc: subprocess.CalledProcessError, limit: int = 600) -> str:
    raw = exc.stderr or b""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    return text[-limit:]
