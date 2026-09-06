"""Тонка обгортка над googleapiclient для роботи з YouTube Data API v3.

Використовує лише search.list / videos.list / channels.list / playlistItems.list
і рахує витрачені одиниці квоти через app.quota.quota.
"""

import os
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .quota import quota

SEARCH_COST = 100
LIST_COST = 1

# Офіційне визначення YouTube Shorts (з жовтня 2024) — відео тривалістю до 3 хвилин.
SHORT_THRESHOLD_SECONDS = 180

# Скільки відео максимум тягнемо для графіка росту каналу (запобіжник квоти на випадок
# каналу з дуже великою кількістю відео). Плейлист завантажень YouTube віддає відео від
# найновіших до найстаріших, тому цей ліміт — це стеля пошуку, а не "перші N" для показу:
# рахунок videos.list коштує 1 unit/50 відео незалежно від їхньої кількості, тож тягнути
# все до цієї стелі дешево, а обрізати список для показу вже після сортування за датою
# (див. CHART_DISPLAY_CAP), щоб не загубити справді перше відео каналу.
MAX_GROWTH_VIDEOS = 1000

# Скільки точок максимум показуємо на графіку/в таблиці (читабельність UI). Якщо відео
# більше — рівномірно розріджуємо хронологію, завжди залишаючи перше, останнє, пік і прорив.
CHART_DISPLAY_CAP = 250

_client = None

_DURATION_RE = re.compile(
    r"P(?:\d+Y)?(?:\d+M)?(?:\d+D)?T?(?:(?P<h>\d+)H)?(?:(?P<m>\d+)M)?(?:(?P<s>\d+)S)?"
)


class YouTubeApiError(Exception):
    """Помилка звернення до YouTube API з людяним повідомленням для UI."""


def get_client():
    global _client
    if _client is None:
        api_key = os.environ.get("YOUTUBE_API_KEY")
        if not api_key:
            raise YouTubeApiError(
                "YOUTUBE_API_KEY не знайдено. Створи файл .env на основі .env.example "
                "і встав туди свій ключ (інструкція в README.md)."
            )
        _client = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
    return _client


def _handle_http_error(exc: HttpError) -> YouTubeApiError:
    status = getattr(exc.resp, "status", None)
    body = str(exc)
    if status == 403 and ("quotaExceeded" in body or "dailyLimitExceeded" in body):
        return YouTubeApiError(
            "Вичерпано денну квоту YouTube Data API (типово 10 000 unit/добу). "
            "Спробуй завтра або створи новий проєкт/ключ у Google Cloud Console."
        )
    if status == 400:
        return YouTubeApiError(f"Некоректний запит до YouTube API: {exc}")
    if status == 404:
        return YouTubeApiError("YouTube API не знайшов запитані дані.")
    return YouTubeApiError(f"Помилка YouTube API: {exc}")


def published_after_iso(days: int | None) -> str | None:
    if not days:
        return None
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso8601_duration(value: str | None) -> int:
    """PT1H2M3S -> кількість секунд. Повертає 0, якщо розпарсити не вдалось."""
    if not value:
        return 0
    match = _DURATION_RE.fullmatch(value)
    if not match:
        return 0
    h = int(match.group("h") or 0)
    m = int(match.group("m") or 0)
    s = int(match.group("s") or 0)
    return h * 3600 + m * 60 + s


def _search_videos_page(
    client,
    keyword: str,
    region_code: str,
    published_after: str | None,
    pages: int,
    video_duration: str | None,
) -> list[dict]:
    """Один прохід пошуку (до `pages` сторінок) з опційним фільтром videoDuration."""
    results: list[dict] = []
    page_token = None
    extra = {"videoDuration": video_duration} if video_duration else {}
    for _ in range(pages):
        request = client.search().list(
            part="snippet",
            q=keyword,
            type="video",
            order="viewCount",
            regionCode=region_code,
            maxResults=50,
            pageToken=page_token,
            publishedAfter=published_after,
            **extra,
        )
        response = request.execute()
        quota.add(SEARCH_COST)
        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            snippet = item.get("snippet", {})
            channel_id = snippet.get("channelId")
            if not video_id or not channel_id:
                continue
            results.append(
                {
                    "video_id": video_id,
                    "channel_id": channel_id,
                    "title": snippet.get("title"),
                    "published_at": snippet.get("publishedAt"),
                    "keyword": keyword,
                }
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def search_videos(
    keyword: str,
    region_code: str,
    published_after: str | None,
    pages: int,
    video_type: str = "all",
) -> list[dict]:
    """Шукає відео за ключовим словом, повертає сирі збіги (video_id, channel_id, ...).

    "order=viewCount" без звуження за тривалістю здебільшого повертає Shorts (вони мають
    найбільше переглядів у більшості ніш) — тож для "long" НЕ можна просто відсортувати
    за переглядами і відфільтрувати Shorts постфактум: результатів лишалось би одиниці.
    Тому для "long" явно опитуємо YouTube окремо по бакетах videoDuration=medium (4-20 хв)
    і long (>20 хв) та об'єднуємо — ціна: 2x SEARCH_COST на сторінку замість 1x.
    """
    client = get_client()
    try:
        if video_type == "short":
            return _search_videos_page(client, keyword, region_code, published_after, pages, "short")
        if video_type == "long":
            medium = _search_videos_page(client, keyword, region_code, published_after, pages, "medium")
            long_ = _search_videos_page(client, keyword, region_code, published_after, pages, "long")
            seen: set[str] = set()
            merged = []
            for hit in medium + long_:
                if hit["video_id"] not in seen:
                    seen.add(hit["video_id"])
                    merged.append(hit)
            return merged
        return _search_videos_page(client, keyword, region_code, published_after, pages, None)
    except HttpError as exc:
        raise _handle_http_error(exc) from exc


def get_video_details(video_ids: Iterable[str]) -> dict[str, dict]:
    """Повертає {video_id: {views, duration_seconds, is_short}}.

    search.list не містить реальних переглядів чи тривалості — тому окремий виклик.
    """
    client = get_client()
    details: dict[str, dict] = {}
    ids = list(dict.fromkeys(video_ids))
    try:
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = client.videos().list(part="statistics,contentDetails", id=",".join(batch)).execute()
            quota.add(LIST_COST)
            for item in response.get("items", []):
                duration_seconds = _parse_iso8601_duration(item.get("contentDetails", {}).get("duration"))
                details[item["id"]] = {
                    "views": int(item.get("statistics", {}).get("viewCount", 0)),
                    "duration_seconds": duration_seconds,
                    "is_short": duration_seconds > 0 and duration_seconds <= SHORT_THRESHOLD_SECONDS,
                }
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return details


def get_channels(channel_ids: Iterable[str]) -> dict[str, dict]:
    """Повертає {channel_id: {title, country, published_at, video_count, subscriber_count,
    view_count, uploads_playlist_id}}."""
    client = get_client()
    channels: dict[str, dict] = {}
    ids = list(dict.fromkeys(channel_ids))
    try:
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = (
                client.channels()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            quota.add(LIST_COST)
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                uploads_playlist_id = (
                    item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                )
                channels[item["id"]] = {
                    "title": snippet.get("title"),
                    "country": snippet.get("country"),
                    "published_at": snippet.get("publishedAt"),
                    "video_count": int(stats.get("videoCount", 0)),
                    "subscriber_count": 0
                    if stats.get("hiddenSubscriberCount")
                    else int(stats.get("subscriberCount", 0)),
                    "view_count": int(stats.get("viewCount", 0)),
                    "uploads_playlist_id": uploads_playlist_id,
                }
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return channels


def get_playlist_video_ids(playlist_id: str, max_videos: int = MAX_GROWTH_VIDEOS) -> tuple[list[str], bool]:
    """Повертає (video_ids, truncated) — ID усіх відео плейлиста завантажень каналу,
    обмежено max_videos для контролю квоти."""
    client = get_client()
    ids: list[str] = []
    page_token = None
    truncated = False
    try:
        while len(ids) < max_videos:
            response = (
                client.playlistItems()
                .list(part="contentDetails", playlistId=playlist_id, maxResults=50, pageToken=page_token)
                .execute()
            )
            quota.add(LIST_COST)
            for item in response.get("items", []):
                vid = item.get("contentDetails", {}).get("videoId")
                if vid:
                    ids.append(vid)
            page_token = response.get("nextPageToken")
            if not page_token:
                break
        if page_token and len(ids) >= max_videos:
            truncated = True
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return ids[:max_videos], truncated


def get_videos_full(video_ids: Iterable[str]) -> dict[str, dict]:
    """Як get_video_details, але з title/published_at (part=snippet,statistics,contentDetails)."""
    client = get_client()
    details: dict[str, dict] = {}
    ids = list(dict.fromkeys(video_ids))
    try:
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = (
                client.videos()
                .list(part="snippet,statistics,contentDetails", id=",".join(batch))
                .execute()
            )
            quota.add(LIST_COST)
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                duration_seconds = _parse_iso8601_duration(item.get("contentDetails", {}).get("duration"))
                details[item["id"]] = {
                    "title": snippet.get("title"),
                    "published_at": snippet.get("publishedAt"),
                    "views": int(item.get("statistics", {}).get("viewCount", 0)),
                    "duration_seconds": duration_seconds,
                    "is_short": duration_seconds > 0 and duration_seconds <= SHORT_THRESHOLD_SECONDS,
                }
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return details


def get_channel_growth(channel_id: str) -> dict:
    """Оркеструє повний таймлайн відео каналу для графіка росту.

    Повертає dict сумісний із schemas.ChannelGrowth (без валідації тут).
    """
    warnings: list[str] = []
    channels = get_channels([channel_id])
    channel = channels.get(channel_id)
    if not channel:
        raise YouTubeApiError("Канал не знайдено або він видалений/приватний.")

    uploads_playlist_id = channel.get("uploads_playlist_id")
    if not uploads_playlist_id:
        raise YouTubeApiError("Не вдалось знайти плейлист завантажень цього каналу.")

    video_ids, truncated = get_playlist_video_ids(uploads_playlist_id)
    if truncated:
        warnings.append(
            f"У каналу більше {MAX_GROWTH_VIDEOS} відео — показано {MAX_GROWTH_VIDEOS} найновіших, "
            "тому графік міг не дотягнутись до справді першого відео каналу."
        )

    videos_raw = get_videos_full(video_ids)

    videos = []
    for vid in video_ids:
        raw = videos_raw.get(vid)
        if not raw or not raw.get("published_at"):
            continue
        videos.append(
            {
                "video_id": vid,
                "title": raw.get("title") or vid,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "published_at": raw["published_at"],
                "view_count": raw.get("views", 0),
                "duration_seconds": raw.get("duration_seconds", 0),
                "is_short": raw.get("is_short", False),
            }
        )

    videos.sort(key=lambda v: v["published_at"])

    cumulative = 0
    prior_views: list[int] = []
    peak_idx = None
    breakout_idx = None
    for idx, v in enumerate(videos):
        cumulative += v["view_count"]
        v["cumulative_views"] = cumulative
        v["is_breakout"] = False
        v["is_peak"] = False

        if peak_idx is None or v["view_count"] > videos[peak_idx]["view_count"]:
            peak_idx = idx

        if breakout_idx is None and prior_views:
            rolling_avg = sum(prior_views) / len(prior_views)
            if rolling_avg > 0 and v["view_count"] >= rolling_avg * 3:
                breakout_idx = idx
        prior_views.append(v["view_count"])

    if peak_idx is not None:
        videos[peak_idx]["is_peak"] = True
    if breakout_idx is not None:
        videos[breakout_idx]["is_breakout"] = True

    display_videos = videos
    if len(videos) > CHART_DISPLAY_CAP:
        # Рівномірно розріджуємо хронологію для читабельності UI, але завжди залишаємо
        # перше й останнє відео (щоб не втратити "від першого відео до сьогодні") та
        # позначені пік/прорив — інакше найважливіші точки могли б випасти з вибірки.
        keep = {0, len(videos) - 1}
        if peak_idx is not None:
            keep.add(peak_idx)
        if breakout_idx is not None:
            keep.add(breakout_idx)
        step = len(videos) / CHART_DISPLAY_CAP
        keep.update(int(i * step) for i in range(CHART_DISPLAY_CAP))
        display_videos = [videos[i] for i in sorted(keep)]
        warnings.append(
            f"Канал має {len(videos)} відео в аналізі — на графіку показано {len(display_videos)} "
            "рівномірно розподілених точок (включно з першим/останнім відео, піком і проривом) "
            "для читабельності."
        )

    return {
        "channel_id": channel_id,
        "channel_title": channel.get("title") or channel_id,
        "videos": display_videos,
        "truncated": truncated,
        "warnings": warnings,
    }
