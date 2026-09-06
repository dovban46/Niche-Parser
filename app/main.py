from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import history
from .quota import DEFAULT_DAILY_QUOTA, quota
from .schemas import (
    ChannelGrowth,
    ChannelResult,
    SearchHistoryDetail,
    SearchHistoryItem,
    SearchRequest,
    SearchResponse,
)
from .scoring import build_channel_result, passes_filters
from .youtube_client import (
    YouTubeApiError,
    get_channel_growth,
    get_channels,
    get_video_details,
    published_after_iso,
    search_videos,
)

load_dotenv()
history.init_db()

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="YouTube Niche Parser")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")


def _static_version() -> str:
    """Час модифікації app.js/style.css — підставляється в URL статики (?v=...),
    щоб браузер завжди підвантажував свіжу версію після наших правок і не тримав
    старий JS/CSS у кеші (саме це раніше маскувалось під "фільтри не працюють")."""
    try:
        mtimes = [
            (STATIC_DIR / "app.js").stat().st_mtime,
            (STATIC_DIR / "style.css").stat().st_mtime,
        ]
        return str(int(max(mtimes)))
    except OSError:
        return "0"

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
            "quota_remaining": quota.remaining,
            "daily_quota": DEFAULT_DAILY_QUOTA,
            "static_version": _static_version(),
        },
    )


@app.get("/api/quota")
def api_quota():
    return {"quota_used_today": quota.used, "quota_remaining": quota.remaining, "daily_quota": DEFAULT_DAILY_QUOTA}


def _make_response(results: list[ChannelResult], channels_scanned: int, warnings: list[str]) -> SearchResponse:
    return SearchResponse(
        results=results,
        quota_used_today=quota.used,
        quota_remaining=quota.remaining,
        channels_scanned=channels_scanned,
        warnings=warnings,
    )


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
            hits = search_videos(kw, req.region_code, published_after, req.pages_per_keyword, req.video_type)
            video_hits.extend(hits)
        except YouTubeApiError as exc:
            warnings.append(f'"{kw}": {exc}')

    if not video_hits:
        response = _make_response([], 0, warnings)
        _save_history(req, response)
        return response

    video_ids = [h["video_id"] for h in video_hits]
    try:
        details = get_video_details(video_ids)
    except YouTubeApiError as exc:
        warnings.append(str(exc))
        details = {}

    filtered_hits = []
    for h in video_hits:
        d = details.get(h["video_id"], {"views": 0, "duration_seconds": 0, "is_short": False})
        h["views"] = d["views"]
        h["duration_seconds"] = d["duration_seconds"]
        h["is_short"] = d["is_short"]

        # Точна фільтрація за типом відео (videoDuration=short з search.list — лише грубий пре-фільтр).
        if req.video_type == "short" and not h["is_short"]:
            continue
        if req.video_type == "long" and h["is_short"]:
            continue
        # Поріг переглядів саме на знайденому відео (а не в середньому по каналу).
        if req.min_video_views is not None and h["views"] < req.min_video_views:
            continue

        filtered_hits.append(h)

    matches_by_channel: dict[str, dict] = {}
    for h in filtered_hits:
        entry = matches_by_channel.setdefault(h["channel_id"], {"keywords": set(), "top_video": None})
        entry["keywords"].add(h["keyword"])
        if entry["top_video"] is None or h["views"] > entry["top_video"]["views"]:
            entry["top_video"] = h

    if not matches_by_channel:
        response = _make_response([], 0, warnings)
        _save_history(req, response)
        return response

    try:
        channels_raw = get_channels(matches_by_channel.keys())
    except YouTubeApiError as exc:
        response = _make_response([], 0, warnings + [str(exc)])
        _save_history(req, response)
        return response

    results: list[ChannelResult] = []
    for channel_id, raw in channels_raw.items():
        match = matches_by_channel[channel_id]
        channel_result = build_channel_result(
            channel_id, raw, sorted(match["keywords"]), match["top_video"]
        )
        if passes_filters(channel_result, req):
            results.append(channel_result)

    results.sort(key=lambda c: c.score, reverse=True)

    response = _make_response(results, len(channels_raw), warnings)
    _save_history(req, response)
    return response


def _save_history(req: SearchRequest, response: SearchResponse) -> None:
    try:
        history.save_search(req.model_dump(), response.model_dump())
    except Exception:
        # Історія не має ламати основний пошук, якщо запис на диск не вдався.
        pass


@app.get("/api/history", response_model=list[SearchHistoryItem])
def api_history_list(limit: int = 50):
    return history.list_searches(limit=limit)


@app.get("/api/history/{search_id}", response_model=SearchHistoryDetail)
def api_history_get(search_id: int):
    record = history.get_search(search_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Запис історії не знайдено.")
    return record


@app.delete("/api/history/{search_id}")
def api_history_delete(search_id: int):
    deleted = history.delete_search(search_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Запис історії не знайдено.")
    return {"deleted": True}


@app.get("/api/channel/{channel_id}/growth", response_model=ChannelGrowth)
def api_channel_growth(channel_id: str):
    try:
        return get_channel_growth(channel_id)
    except YouTubeApiError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
