"""Тонка обгортка над googleapiclient для роботи з YouTube Data API v3.

Використовує лише search.list / videos.list / channels.list і рахує
витрачені одиниці квоти через app.quota.quota.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Iterable

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .quota import quota

SEARCH_COST = 100
LIST_COST = 1

_client = None


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


def search_videos(keyword: str, region_code: str, published_after: str | None, pages: int) -> list[dict]:
    """Шукає відео за ключовим словом, повертає сирі збіги (video_id, channel_id, ...)."""
    client = get_client()
    results: list[dict] = []
    page_token = None
    try:
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
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return results


def get_video_stats(video_ids: Iterable[str]) -> dict[str, int]:
    """Повертає {video_id: viewCount} — search.list не містить реальних переглядів."""
    client = get_client()
    stats: dict[str, int] = {}
    ids = list(dict.fromkeys(video_ids))
    try:
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = client.videos().list(part="statistics", id=",".join(batch)).execute()
            quota.add(LIST_COST)
            for item in response.get("items", []):
                stats[item["id"]] = int(item.get("statistics", {}).get("viewCount", 0))
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return stats


def get_channels(channel_ids: Iterable[str]) -> dict[str, dict]:
    """Повертає {channel_id: {title, country, published_at, video_count, subscriber_count, view_count}}."""
    client = get_client()
    channels: dict[str, dict] = {}
    ids = list(dict.fromkeys(channel_ids))
    try:
        for i in range(0, len(ids), 50):
            batch = ids[i : i + 50]
            response = client.channels().list(part="snippet,statistics", id=",".join(batch)).execute()
            quota.add(LIST_COST)
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                channels[item["id"]] = {
                    "title": snippet.get("title"),
                    "country": snippet.get("country"),
                    "published_at": snippet.get("publishedAt"),
                    "video_count": int(stats.get("videoCount", 0)),
                    "subscriber_count": 0
                    if stats.get("hiddenSubscriberCount")
                    else int(stats.get("subscriberCount", 0)),
                    "view_count": int(stats.get("viewCount", 0)),
                }
    except HttpError as exc:
        raise _handle_http_error(exc) from exc
    return channels
