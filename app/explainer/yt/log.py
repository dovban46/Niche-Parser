"""Журнал каналу: знімки публічної статистики (Data API) + ручні дані Studio (утримання, «переглянуто vs пропущено») по кожному відео.
Файли: storage/channel_log/snapshots.jsonl (дописується), storage/channel_log/studio.json (slug → метрики), storage/channel_log/map.json (video_id → slug)."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LOG = ROOT / "storage" / "channel_log"
SNAP = LOG / "snapshots.jsonl"
STUDIO = LOG / "studio.json"
MAP = LOG / "map.json"
VIDEOS = ROOT / "videos"
JOBS = ROOT / "storage" / "explainer_jobs"


def _load(p: Path, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _save(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")


def norm(t: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()


def slug_titles() -> dict[str, list[str]]:
    """slug → назви з metadata.txt (користувач обирає одну з трьох, тому звіряємо з усіма)."""
    out = {}
    for d in sorted(VIDEOS.glob("s*-*")):
        m = d / "metadata.txt"
        if not m.exists():
            continue
        titles = re.findall(r"^\d\.\s+(.+?)\s+\(\d+\)\s*$", m.read_text(encoding="utf-8"), re.M)
        out[d.name] = titles
    return out


def match_slug(title: str, known: dict[str, list[str]] | None = None) -> str | None:
    known = known or slug_titles()
    n = norm(title)
    for slug, ts in known.items():
        if any(norm(t) == n for t in ts):
            return slug
    return None


def job_info(slug: str) -> dict:
    """Параметри відео з його теки: тривалість, слова, стиль, хук (для порівняння «що працює»)."""
    j = JOBS / slug
    info = {"slug": slug}
    beats = _load(j / "beats.json", [])
    design = _load(j / "design.json", {})
    if beats:
        info["words"] = sum(len(str(b.get("t", "")).split()) for b in beats)
        info["hook"] = (beats[0].get("hook") or beats[0].get("t", "")).replace("|", " ")
        info["beats"] = len(beats)
        info["cards"] = sorted({b["card"].get("type") for b in beats if isinstance(b.get("card"), dict)})
    st = design.get("style") or {}
    info["kit"] = _kit_name(st) if st else "cartoon"
    info["topic"] = design.get("topic", "")
    info["art"] = design.get("art", "")
    return info


def _kit_name(st: dict) -> str:
    try:
        from .. import style_kit as k
        for name in ("POSTER", "NAVAL", "HERALDIC", "DOSSIER", "SERIOUS_C", "SERIOUS_B", "SERIOUS"):
            if dict(getattr(k, name)) == {kk: st.get(kk) for kk in getattr(k, name)}:
                return name.lower()
    except Exception:   # noqa: BLE001
        pass
    return st.get("look", "mixed") + "/" + str(st.get("cta", ""))


def studio_set(slug: str, **metrics) -> None:
    d = _load(STUDIO, {})
    d.setdefault(slug, {}).update({k: v for k, v in metrics.items() if v is not None})
    d[slug]["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _save(STUDIO, d)
