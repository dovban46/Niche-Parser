"""Видача: лише відео, прев'ю й метадані → videos/jp_<slug>/."""

import shutil
from pathlib import Path

from ..config import VIDEOS_ROOT
from . import core, thumbs


def metadata_text(meta: dict, versions: list[dict] | None = None) -> str:
    lines = ["TITLE OPTIONS (matched with the thumbnails; no shared meaningful words, lint-checked):"]
    for i, v in enumerate(versions or thumbs.VERSIONS, start=1):
        lines.append(f"  {i}. {v['title']}   <->   thumbnail_{i}.jpg: «{v['text']}»")
    lines += ["", "DESCRIPTION:", meta["description"], "", "TAGS:", ", ".join(meta["tags"]), "",
              "PINNED COMMENT:", meta["pinned_comment"], "", "UPLOAD NOTES:"] + [f"  - {n}" for n in meta["upload_notes"]]
    return core.NL.join(lines) + core.NL


def ship(slug: str, log=print) -> Path:
    d = core.job_dir(slug)
    meta = core.load_json(d / "metadata.json")
    out = VIDEOS_ROOT / f"jp_{slug}"
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(d / "video_upload.mp4" if (d / "video_upload.mp4").exists() else d / "video.mp4", out / "video.mp4")
    n_thumbs = len(thumbs.versions_for(slug))      # лише версії з thumbs.json (запасні alt_versions лишаються в storage)
    for i in (1, 2, 3):   # у видачі лише відео, прев'ю й метадані (сценарій і факти лишаються в storage/jp_jobs)
        src, dst = d / "thumbs" / f"thumbnail_{i}.jpg", out / f"thumbnail_{i}.jpg"
        if i <= n_thumbs and src.exists():
            shutil.copy2(src, dst)
        elif dst.exists():
            dst.unlink()
    (out / "metadata.txt").write_text(metadata_text(meta, thumbs.versions_for(slug)), encoding="utf-8-sig")
    log(f"видано: {out}")
    return out
