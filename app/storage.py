"""Шляхи до файлових артефактів одного job'а на диску.

storage/jobs/{id}/{script,audio,visuals,video,qa,metadata,logs}/...
"""

from pathlib import Path

from .config import STORAGE_ROOT


class JobStorage:
    def __init__(self, job_id: int):
        self.job_id = job_id
        self.job_root = STORAGE_ROOT / "jobs" / str(job_id)

    def ensure_dirs(self) -> None:
        for d in (
            self.script_dir(),
            self.audio_dir(),
            self.visuals_dir(),
            self.video_dir(),
            self.qa_dir(),
            self.metadata_dir(),
            self.metadata_dir() / "thumbnails",
            self.logs_dir(),
        ):
            d.mkdir(parents=True, exist_ok=True)

    def script_dir(self) -> Path:
        return self.job_root / "script"

    def audio_dir(self) -> Path:
        return self.job_root / "audio"

    def visuals_dir(self) -> Path:
        return self.job_root / "visuals"

    def video_dir(self) -> Path:
        return self.job_root / "video"

    def qa_dir(self) -> Path:
        return self.job_root / "qa"

    def metadata_dir(self) -> Path:
        return self.job_root / "metadata"

    def logs_dir(self) -> Path:
        return self.job_root / "logs"

    def relative(self, path: Path) -> str:
        """Шлях відносно STORAGE_ROOT — саме таким віддається клієнту (роздається як
        /storage/<relative>, бо STORAGE_ROOT змонтовано в FastAPI як StaticFiles)."""
        return str(path.resolve().relative_to(STORAGE_ROOT.resolve())).replace("\\", "/")
