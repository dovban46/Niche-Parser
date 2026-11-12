"""Stub-реалізація VideoGenProvider — без ключів і без витрат. Замість справжньої анімації робить
плавний "наїзд" камери на стартовий кадр через ffmpeg — цього досить, щоб пройшов увесь тракт
кліпів (тривалість, підгонка під озвучку, склейка), поки не підключено Veo."""

import subprocess
from pathlib import Path

from ...config import VIDEO_FPS, VIDEO_HEIGHT, VIDEO_WIDTH
from ...ffutil import error_tail, run_ffmpeg
from ..base import ProviderConfigError, VideoGenProvider


class StubVideoGenProvider(VideoGenProvider):
    supported_durations = (4, 6, 8)
    cost_per_second_usd = 0.0

    def generate_clip(self, prompt: str, start_image: Path, out_path: Path, duration_s: int) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        frames = duration_s * VIDEO_FPS
        vf = (
            "scale=3840:2160:flags=lanczos,"
            f"zoompan=z='1+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}"
            f":s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={VIDEO_FPS},format=yuv420p"
        )
        try:
            run_ffmpeg(["-i", str(start_image), "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264",
                        "-preset", "veryfast", "-crf", "20", "-an", str(out_path)])
        except subprocess.CalledProcessError as exc:
            raise ProviderConfigError(f"Stub-кліп: ffmpeg завершився з помилкою: {error_tail(exc)}") from exc
        return out_path
