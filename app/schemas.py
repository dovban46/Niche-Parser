from typing import Literal

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, description="Список ключових слів/фраз")
    region_code: str = Field("US", min_length=2, max_length=2)
    published_after_days: int | None = Field(
        90, ge=0, description="Шукати відео, опубліковані за останні N днів (0 = без обмеження)"
    )
    pages_per_keyword: int = Field(1, ge=1, le=3, description="К-сть сторінок пошуку (по 50) на кожне слово")
    video_type: Literal["all", "short", "long"] = Field(
        "all", description="Тип відео: всі / тільки Shorts (≤180с) / тільки довгі (>180с)"
    )
    min_views_per_video: int | None = Field(
        None, ge=0, description="Мін. середні перегляди/відео по каналу (опційно)"
    )
    min_video_views: int | None = Field(
        None, ge=0, description="Мін. перегляди саме на знайденому відео (для пошуку 'гарячих' відео за період)"
    )
    max_video_count: int = Field(30, ge=1)
    max_channel_age_months: int = Field(12, ge=1)
    require_small_or_new: bool = Field(
        True, description="Якщо False — не вимагати 'канал новий АБО мало відео' (чистий пошук по відео)"
    )
    min_subscribers: int | None = Field(None, ge=0)
    max_subscribers: int | None = Field(None, ge=0)


class ChannelResult(BaseModel):
    channel_id: str
    title: str
    url: str
    country: str | None = None
    created_at: str | None = None
    age_months: float | None = None
    video_count: int
    subscriber_count: int
    total_view_count: int
    views_per_video: float
    views_per_subscriber: float | None = None
    score: float
    matched_keywords: list[str]
    top_video_title: str | None = None
    top_video_views: int | None = None
    top_video_url: str | None = None
    top_video_is_short: bool | None = None


class SearchResponse(BaseModel):
    results: list[ChannelResult]
    # Дефолти 0 — щоб старі записи історії (збережені до появи цих полів,
    # ще під ім'ям quota_used_session) продовжували коректно читатись.
    quota_used_today: int = 0
    quota_remaining: int = 0
    channels_scanned: int
    warnings: list[str] = []


class SearchHistoryItem(BaseModel):
    id: int
    created_at: str
    keywords: list[str]
    region_code: str
    published_after_days: int | None
    video_type: str
    results_count: int
    quota_used: int


class SearchHistoryDetail(SearchHistoryItem):
    params: SearchRequest
    response: SearchResponse


class ChannelVideoPoint(BaseModel):
    video_id: str
    title: str
    url: str
    published_at: str
    view_count: int
    duration_seconds: int
    is_short: bool
    cumulative_views: int
    is_breakout: bool = False
    is_peak: bool = False


class ChannelGrowth(BaseModel):
    channel_id: str
    channel_title: str
    videos: list[ChannelVideoPoint]
    truncated: bool = False
    warnings: list[str] = []
