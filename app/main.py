from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .quota import DEFAULT_DAILY_QUOTA, quota
from .schemas import ChannelResult, SearchRequest, SearchResponse
from .scoring import build_channel_result, passes_filters
from .youtube_client import (
    YouTubeApiError,
    get_channels,
    get_video_stats,
    published_after_iso,
    search_videos,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title="YouTube Niche Parser")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# (код регіону, назва українською) — використовується для regionCode пошуку YouTube
REGIONS = [
    ("US", "США"), ("GB", "Великобританія"), ("CA", "Канада"), ("AU", "Австралія"),
    ("DE", "Німеччина"), ("FR", "Франція"), ("ES", "Іспанія"), ("IT", "Італія"),
    ("PL", "Польща"), ("UA", "Україна"), ("NL", "Нідерланди"), ("BE", "Бельгія"),
    ("BR", "Бразилія"), ("MX", "Мексика"), ("AR", "Аргентина"), ("IN", "Індія"),
    ("ID", "Індонезія"), ("PH", "Філіппіни"), ("MY", "Малайзія"), ("SG", "Сінгапур"),
    ("TR", "Туреччина"), ("SA", "Саудівська Аравія"), ("AE", "ОАЕ"), ("EG", "Єгипет"),
    ("NG", "Нігерія"), ("ZA", "ПАР"), ("JP", "Японія"), ("KR", "Південна Корея"),
    ("VN", "В'єтнам"), ("TH", "Таїланд"), ("PT", "Португалія"), ("CZ", "Чехія"),
    ("RO", "Румунія"), ("SE", "Швеція"), ("NO", "Норвегія"), ("IL", "Ізраїль"),
]


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "regions": REGIONS,
            "quota_used": quota.used,
            "daily_quota": DEFAULT_DAILY_QUOTA,
        },
    )


@app.get("/api/quota")
def api_quota():
    return {"quota_used_session": quota.used, "daily_quota": DEFAULT_DAILY_QUOTA}


@app.post("/api/search", response_model=SearchResponse)
def api_search(req: SearchRequest):
    warnings: list[str] = []

    try:
        published_after = published_after_iso(req.published_after_days)
    except Exception:
        published_after = None

    video_hits: list[dict] = []
    for kw in req.keywords:
        kw = kw.strip()
        if not kw:
            continue
        try:
            hits = search_videos(kw, req.region_code, published_after, req.pages_per_keyword)
            video_hits.extend(hits)
        except YouTubeApiError as exc:
            warnings.append(f'"{kw}": {exc}')

    if not video_hits:
        return SearchResponse(
            results=[], quota_used_session=quota.used, channels_scanned=0, warnings=warnings
        )

    video_ids = [h["video_id"] for h in video_hits]
    try:
        view_stats = get_video_stats(video_ids)
    except YouTubeApiError as exc:
        warnings.append(str(exc))
        view_stats = {}

    matches_by_channel: dict[str, dict] = {}
    for h in video_hits:
        h["views"] = view_stats.get(h["video_id"], 0)
        entry = matches_by_channel.setdefault(h["channel_id"], {"keywords": set(), "top_video": None})
        entry["keywords"].add(h["keyword"])
        if entry["top_video"] is None or h["views"] > entry["top_video"]["views"]:
            entry["top_video"] = h

    try:
        channels_raw = get_channels(matches_by_channel.keys())
    except YouTubeApiError as exc:
        return SearchResponse(
            results=[],
            quota_used_session=quota.used,
            channels_scanned=0,
            warnings=warnings + [str(exc)],
        )

    results: list[ChannelResult] = []
    for channel_id, raw in channels_raw.items():
        match = matches_by_channel[channel_id]
        channel_result = build_channel_result(
            channel_id, raw, sorted(match["keywords"]), match["top_video"]
        )
        if passes_filters(channel_result, req):
            results.append(channel_result)

    results.sort(key=lambda c: c.score, reverse=True)

    return SearchResponse(
        results=results,
        quota_used_session=quota.used,
        channels_scanned=len(channels_raw),
        warnings=warnings,
    )
