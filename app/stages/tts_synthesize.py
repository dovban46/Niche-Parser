import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

from ..config import STORAGE_ROOT, TTS_PROVIDER
from ..ffutil import error_tail, have_ffmpeg, probe_duration, run_ffmpeg
from ..providers.registry import get_tts_provider
from .base import StageContext, StageResult

_ELEVENLABS_USD_PER_CHAR = 0.0001  # $0.10 за 1000 символів


def job_voice(ctx: StageContext) -> str | None:
    """Голос з UI діє лише для провайдера, під який його обирали (ID ElevenLabs не годиться edge-tts)."""
    return ctx.job["voice_id"] if ctx.config.get("tts_provider") == TTS_PROVIDER else None


class TtsSynthesizeStage:
    """Озвучка по сегментах (кожен — окремий виклик, із сусідніми репліками як контекстом інтонації),
    далі склейка в один full_narration. Стадія ідемпотентна: вже озвучені сегменти (платна робота)
    не синтезуються повторно. У тест-режимі (preview_seconds) озвучується лише початок."""

    name = "tts_synthesize"

    def run(self, ctx: StageContext) -> StageResult:
        segments = ctx.repo.list_segments(ctx.job_id)
        if not segments:
            return StageResult(status="failed", error="Немає сегментів — visual_plan не завершився?")

        tts = get_tts_provider()
        ext = tts.file_extension
        audio_dir = ctx.storage.audio_dir()
        voice = job_voice(ctx)
        preview = ctx.job.get("preview_seconds")
        limit_ms = preview * 1000 if preview else None

        texts = [s["text"] for s in segments]
        cumulative_ms = 0
        chars = 0
        errors: dict[int, str] = {}
        voiced: list[dict] = []

        for i, seg in enumerate(segments):
            idx = seg["segment_index"]
            out_path = audio_dir / f"segment_{idx:04d}.{ext}"

            if limit_ms is not None and cumulative_ms >= limit_ms:
                ctx.repo.update_segment(ctx.job_id, idx, status="skipped", audio_path=None, duration_ms=None, start_ms=None)
                continue

            if seg["audio_path"] and out_path.exists():
                duration_ms = int((probe_duration(out_path) or seg["duration_ms"] / 1000) * 1000)
            elif seg.get("pause_seconds"):
                # Пауза-дихання: без голосу — тиша точної тривалості замість виклику TTS (безкоштовно,
                # і без цього full_narration "з'їв" би паузу при склейці сегментів).
                try:
                    duration_ms = _generate_silence(seg["pause_seconds"], ext, out_path)
                except (subprocess.CalledProcessError, RuntimeError) as exc:
                    errors[idx] = f"тиша для паузи: {exc}"[:300]
                    ctx.repo.update_segment(ctx.job_id, idx, status="failed")
                    continue
            else:
                try:
                    duration_ms = tts.synthesize(
                        seg["text"], out_path, ctx.job["language"], voice,
                        previous_text=texts[i - 1] if i > 0 else None,
                        next_text=texts[i + 1] if i + 1 < len(texts) else None,
                    )
                    chars += len(seg["text"])
                except Exception as exc:  # мережевий провайдер може впасти на окремому сегменті
                    errors[idx] = f"{type(exc).__name__}: {exc}"[:300]
                    ctx.repo.update_segment(ctx.job_id, idx, status="failed")
                    continue

            ctx.repo.update_segment(
                ctx.job_id, idx,
                audio_path=ctx.storage.relative(out_path), duration_ms=duration_ms, start_ms=cumulative_ms,
                status="pending",  # ще чекає на візуал
            )
            cumulative_ms += duration_ms
            voiced.append({**seg, "audio_path": ctx.storage.relative(out_path)})

        if errors:
            return StageResult(
                status="needs_review",
                output={"failed_segments": sorted(errors), "errors": errors, "message": "Частина сегментів не озвучена."},
            )

        output = {
            "segment_count": len(segments),
            "voiced_segments": len(voiced),
            "skipped_segments": len(segments) - len(voiced),
            "audio_format": ext,
            "preview_seconds": preview,
            "estimated_cost_usd": round(chars * _ELEVENLABS_USD_PER_CHAR, 4) if TTS_PROVIDER == "elevenlabs" else 0.0,
        }
        segment_paths = [STORAGE_ROOT / s["audio_path"] for s in voiced]

        if ext == "wav":
            full_path = audio_dir / "full_narration.wav"
            _concat_wavs(segment_paths, full_path)
        elif ext == "mp3" and shutil.which("ffmpeg"):
            full_path = audio_dir / "full_narration.mp3"
            try:
                _concat_mp3s(segment_paths, full_path)
            except subprocess.CalledProcessError as exc:
                return StageResult(status="failed", error=f"ffmpeg (склейка озвучки): {error_tail(exc)}")
        else:
            output["note"] = f"Формат '{ext}' — об'єднаний full_narration не зібрано (ffmpeg не знайдено в PATH)."
            output["total_duration_ms"] = cumulative_ms
            return StageResult(status="success", output=output)

        output["full_narration_path"] = ctx.storage.relative(full_path)
        output["total_duration_ms"] = int((probe_duration(full_path) or cumulative_ms / 1000) * 1000)
        return StageResult(status="success", output=output)


def _generate_silence(seconds: float, ext: str, out_path: Path) -> int:
    """Тиша точної тривалості в тому ж форматі, що й реальна озвучка (щоб конкатенація нижче не бачила
    різниці) — повертає тривалість у мс.
    NOTE: для ext="wav" (edge-tts) параметри (44100/стерео/16-біт) — дефолт, що НЕ обов'язково збігається
    з реальним форматом edge-tts (не перевірено); _concat_wavs просто копіює сирі фрейми під заголовок
    першого файлу, тож розбіжність параметрів дасть артефакт саме на паузі. Для ElevenLabs (mp3, наш
    поточний робочий шлях) це не стосується — libmp3lame сам ресемплить коректно."""
    if not have_ffmpeg():
        raise RuntimeError("ffmpeg не знайдено в PATH — потрібен для генерації тиші паузи-дихання.")
    codec = ["-c:a", "libmp3lame", "-b:a", "128k"] if ext == "mp3" else ["-c:a", "pcm_s16le"]
    run_ffmpeg([
        "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", f"{seconds:.3f}", *codec, str(out_path),
    ])
    return round(seconds * 1000)


def _concat_wavs(paths: list, out_path) -> None:
    if not paths:
        return
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()

    with wave.open(str(out_path), "wb") as out_wav:
        out_wav.setparams(params)
        for p in paths:
            with wave.open(str(p), "rb") as w:
                out_wav.writeframes(w.readframes(w.getnframes()))


def _concat_mp3s(paths: list[Path], out_path: Path) -> None:
    """Об'єднує mp3-сегменти через ffmpeg concat demuxer з переенкодом (libmp3lame),
    щоб уникнути тріскачок на межах фреймів між окремими TTS-викликами."""
    if not paths:
        return

    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as list_file:
        for p in paths:
            escaped = p.resolve().as_posix().replace("'", "'\\''")
            list_file.write(f"file '{escaped}'\n")
        list_path = list_file.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_path,
                "-c:a", "libmp3lame", "-b:a", "128k", str(out_path),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        Path(list_path).unlink(missing_ok=True)
