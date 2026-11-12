"""Трекер: знімок публічної статистики каналу через YouTube Data API (перегляди, лайки, коментарі, тривалість) → snapshots.jsonl.
Виклик API іде в підпроцесі з теки парсера (там ключ і youtube_client; пакети `app` двох проєктів конфліктують).
Retention/свайпи Data API не віддає — їх вносимо вручну зі Studio (log.studio_set)."""
import json
import subprocess
import sys
from datetime import datetime, timezone

from . import CHANNEL_ID
from .log import MAP, SNAP, _load, _save, match_slug, slug_titles

PARSER = "E:/YouTube/parser"
_SCRIPT = r'''
import json, sys
from dotenv import load_dotenv
load_dotenv(".env")
from app import youtube_client as yt
cid, limit = sys.argv[1], int(sys.argv[2])
ch = yt.get_channels([cid])[cid]
ids, _ = yt.get_playlist_video_ids(ch["uploads_playlist_id"], max_videos=limit)
cl = yt.get_client()
rows = []
for i in range(0, len(ids), 50):
    r = cl.videos().list(part="snippet,statistics,contentDetails", id=",".join(ids[i:i + 50])).execute()
    for it in r.get("items", []):
        st = it.get("statistics", {})
        rows.append({"id": it["id"], "title": it["snippet"]["title"], "published": it["snippet"]["publishedAt"], "duration": it["contentDetails"]["duration"],
                     "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)), "comments": int(st.get("commentCount", 0))})
print("@@JSON@@" + json.dumps(rows))
'''


def snapshot(limit: int = 60) -> list[dict]:
    r = subprocess.run([sys.executable, "-c", _SCRIPT, CHANNEL_ID, str(limit)], cwd=PARSER, capture_output=True, text=True, encoding="utf-8")
    if "@@JSON@@" not in r.stdout:
        raise RuntimeError("tracker: " + (r.stderr or r.stdout)[-400:])
    items = json.loads(r.stdout.split("@@JSON@@", 1)[1])
    known = slug_titles()
    vmap = _load(MAP, {})
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    for it in items:
        slug = vmap.get(it["id"]) or match_slug(it["title"], known)
        if slug:
            vmap[it["id"]] = slug
        rows.append({"t": now, "slug": slug, **it})
    _save(MAP, vmap)
    SNAP.parent.mkdir(parents=True, exist_ok=True)
    with SNAP.open("a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return rows


def latest() -> dict[str, dict]:
    """Останній знімок по кожному відео (id → рядок)."""
    out: dict[str, dict] = {}
    if SNAP.exists():
        for ln in SNAP.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(ln)
            except ValueError:
                continue
            out[r["id"]] = r
    return out


if __name__ == "__main__":
    rows = snapshot()
    print(f"знімок: {len(rows)} відео, сума переглядів {sum(r['views'] for r in rows)}")
