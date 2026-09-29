"""Систематичний скан ніш × мов/гео поверх існуючого youtube_client (той самий лічильник квоти).

Ідея вибірки: для пари (ніша, гео) беремо ТОП-відео за переглядами за останні N днів (search.list,
order=viewCount, обраний бакет тривалості) — це "що реально дивляться зараз". Далі дешево (1 unit на 50 обʼєктів)
збагачуємо відео й канали й рахуємо сигнали:
  • попит — перегляди топ-відео;
  • "молодість" — скільки каналів у топі створено недавно й з якими переглядами при малих підписниках;
  • конкуренція — концентрація переглядів у кількох каналах, к-сть різних каналів у топі.
Результат кожної пари зберігається в app/data/scans/*.json одразу (скан можна перервати й продовжити — пари, що
вже пораховані, пропускаються).

RPM API не віддає (це приватні дані власників каналів), тому він тут не рахується — накладається зовні за гео.
"""

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

from googleapiclient.errors import HttpError

from . import youtube_client as yt
from .quota import quota

SCAN_DIR = Path(__file__).resolve().parent / "data" / "scans"
YOUNG_MONTHS = 18  # канал "молодий", якщо створений не раніше ніж 18 міс тому
SMALL_SUBS = 100_000  # "малий" канал для сигналу прориву
BREAKOUT_VIEWS = 50_000  # відео такого рівня на малому молодому каналі = сигнал прориву


def _age_months(created: str | None) -> float | None:
    if not created:
        return None
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((datetime.now(timezone.utc) - dt).days / 30.44, 1)


def search_top(keyword: str, region: str, language: str, days: int, duration: str | None, pages: int = 1) -> list[dict]:
    """Топ-відео за переглядами за останні `days` днів. duration: short|medium|long|None. Кожна сторінка = 100 unit."""
    client = yt.get_client()
    published_after = yt.published_after_iso(days)
    extra = {"videoDuration": duration} if duration else {}
    hits: list[dict] = []
    token = None
    try:
        for _ in range(pages):
            response = client.search().list(
                part="snippet", q=keyword, type="video", order="viewCount", regionCode=region,
                relevanceLanguage=language, maxResults=50, pageToken=token, publishedAfter=published_after, **extra,
            ).execute()
            quota.add(yt.SEARCH_COST)
            for item in response.get("items", []):
                vid, ch = item.get("id", {}).get("videoId"), item.get("snippet", {}).get("channelId")
                if vid and ch:
                    hits.append({"video_id": vid, "channel_id": ch, "title": item["snippet"].get("title"),
                                 "published_at": item["snippet"].get("publishedAt")})
            token = response.get("nextPageToken")
            if not token:
                break
    except HttpError as exc:
        raise yt._handle_http_error(exc) from exc
    return hits


def video_languages(video_ids: list[str]) -> dict[str, dict]:
    """{video_id: {audio_lang, default_lang}} — мова аудіо/метаданих із snippet (1 unit на 50 відео)."""
    client = yt.get_client()
    out: dict[str, dict] = {}
    ids = list(dict.fromkeys(video_ids))
    try:
        for i in range(0, len(ids), 50):
            response = client.videos().list(part="snippet", id=",".join(ids[i:i + 50])).execute()
            quota.add(yt.LIST_COST)
            for item in response.get("items", []):
                sn = item.get("snippet", {})
                out[item["id"]] = {"audio_lang": (sn.get("defaultAudioLanguage") or "").lower(),
                                   "default_lang": (sn.get("defaultLanguage") or "").lower()}
    except HttpError as exc:
        raise yt._handle_http_error(exc) from exc
    return out


def enrich(hits: list[dict]) -> list[dict]:
    videos = yt.get_video_details([h["video_id"] for h in hits])
    channels = yt.get_channels(list(dict.fromkeys(h["channel_id"] for h in hits)))
    langs = video_languages([h["video_id"] for h in hits])
    rows = []
    for h in hits:
        v, c = videos.get(h["video_id"]), channels.get(h["channel_id"])
        if not v or not c:
            continue
        rows.append({
            **h, **langs.get(h["video_id"], {"audio_lang": "", "default_lang": ""}),
            "views": v["views"], "duration_s": v["duration_seconds"], "is_short": v["is_short"],
            "ch_title": c["title"], "ch_created": c["published_at"], "ch_age_m": _age_months(c["published_at"]),
            "ch_subs": c["subscriber_count"], "ch_videos": c["video_count"], "ch_views": c["view_count"],
            "ch_country": c["country"],
        })
    return rows


# Країни каналів, аудиторія яких переважно має дуже низький RPM (для англомовних тем це часто індійсько-південноазійська аудиторія).
LOW_RPM_COUNTRIES = {"IN", "PK", "BD", "LK", "NP", "ID", "PH", "VN", "NG", "EG", "KE", "GH", "MM", "KH"}
_LATIN_LANGS = {"en", "de", "fr", "es", "it", "pl", "pt", "nl", "sv", "no", "da", "cs", "ro", "tr", "hu", "uk", "ru"}


def latin_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    return sum(ch.isascii() or "\u00c0" <= ch <= "\u024f" for ch in letters) / len(letters) if letters else 1.0


def clean_rows(rows: list[dict], language: str, drop_low_rpm: bool = True) -> list[dict]:
    """Лишає відео потрібною мовою (мова аудіо/метаданих; якщо її не задано — латиниця в назві) і, за потреби,
    без каналів із країн із дуже низьким RPM."""
    out = []
    for r in rows:
        lang = (r.get("audio_lang") or r.get("default_lang") or "")[:2]
        if lang:
            if lang != language:
                continue
        elif latin_ratio(r["title"]) < 0.9:
            continue
        if drop_low_rpm and r.get("ch_country") in LOW_RPM_COUNTRIES:
            continue
        out.append(r)
    return out


def metrics(rows: list[dict]) -> dict:
    """Сигнали ніші за вибіркою топ-відео. Канали рахуємо унікально (найкраще відео каналу в вибірці)."""
    if not rows:
        return {"n_videos": 0}
    by_channel: dict[str, dict] = {}
    for r in rows:
        best = by_channel.get(r["channel_id"])
        if best is None or r["views"] > best["views"]:
            by_channel[r["channel_id"]] = r
    chans = list(by_channel.values())
    total_views = sum(r["views"] for r in rows)
    per_channel_views: dict[str, int] = {}
    for r in rows:
        per_channel_views[r["channel_id"]] = per_channel_views.get(r["channel_id"], 0) + r["views"]
    top3 = sum(sorted(per_channel_views.values(), reverse=True)[:3])

    young = [c for c in chans if c["ch_age_m"] is not None and c["ch_age_m"] <= YOUNG_MONTHS]
    breakouts = [c for c in young if c["ch_subs"] <= SMALL_SUBS and c["views"] >= BREAKOUT_VIEWS]
    young_views = [c["views"] for c in young]
    ratios = [c["views"] / max(c["ch_subs"], 1) for c in young if c["ch_subs"]]
    return {
        "n_videos": len(rows),
        "n_channels": len(chans),
        "total_views": total_views,
        "median_views": int(statistics.median(r["views"] for r in rows)),
        "top3_share": round(top3 / total_views, 3) if total_views else None,
        "young_channels": len(young),
        "young_share": round(len(young) / len(chans), 3),
        "young_views_share": round(sum(r["views"] for r in rows if r["channel_id"] in {c["channel_id"] for c in young}) / total_views, 3) if total_views else None,
        "young_median_views": int(statistics.median(young_views)) if young_views else 0,
        "young_median_views_per_sub": round(statistics.median(ratios), 2) if ratios else None,
        "breakout_channels": len(breakouts),
        "breakout_views_sum": sum(c["views"] for c in breakouts),
    }


def scan_pair(niche: str, keyword: str, region: str, language: str, days: int = 120, duration: str | None = "medium",
              pages: int = 1) -> dict:
    hits = search_top(keyword, region, language, days, duration, pages)
    rows = enrich(hits) if hits else []
    return {"niche": niche, "keyword": keyword, "region": region, "language": language, "days": days,
            "duration": duration, "pages": pages, "scanned_at": datetime.now(timezone.utc).isoformat(),
            "metrics_raw": metrics(rows), "metrics": metrics(clean_rows(rows, language)), "rows": rows}


def load(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def run(grid: list[dict], out_name: str, reserve: int = 300, log=print) -> list[dict]:
    """Проходить grid ([{niche, keyword, region, language, ...}]). Кожен результат дописується у файл одразу;
    вже пораховані пари пропускаються. Зупиняється, коли квоти лишається менше reserve."""
    SCAN_DIR.mkdir(parents=True, exist_ok=True)
    path = SCAN_DIR / out_name
    done = load(path)
    seen = {(d["niche"], d["keyword"], d["region"], d["language"], d["duration"], d["days"]) for d in done}
    for spec in grid:
        key = (spec["niche"], spec["keyword"], spec["region"], spec["language"], spec.get("duration", "medium"), spec.get("days", 120))
        if key in seen:
            continue
        cost = yt.SEARCH_COST * spec.get("pages", 1) + 3
        if quota.remaining < reserve + cost:
            log(f"СТОП: лишилось {quota.remaining} unit (резерв {reserve}).")
            break
        try:
            result = scan_pair(**spec)
        except yt.YouTubeApiError as exc:
            log(f"ПОМИЛКА {key}: {exc}")
            break
        done.append(result)
        path.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
        m = result["metrics"]
        log(f"{spec['niche']:14} {spec['region']} {spec['language']} | відео {m.get('n_videos')} каналів {m.get('n_channels')} "
            f"| медіана {m.get('median_views')} | молодих {m.get('young_channels')} проривів {m.get('breakout_channels')} "
            f"| top3 {m.get('top3_share')} | квота {quota.used}")
    return done
