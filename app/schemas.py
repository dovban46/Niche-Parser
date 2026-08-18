from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    keywords: list[str] = Field(..., min_length=1, description="Список ключових слів/фраз")
    region_code: str = Field("US", min_length=2, max_length=2)
    published_after_days: int | None = Field(
        180, ge=0, description="Шукати відео, опубліковані за останні N днів (0/None = без обмеження)"
    )
    pages_per_keyword: int = Field(1, ge=1, le=3, description="К-сть сторінок пошуку (по 50) на кожне слово")
    min_views_per_video: int = Field(50_000, ge=0)
    max_video_count: int = Field(30, ge=1)
    max_channel_age_months: int = Field(12, ge=1)
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


class SearchResponse(BaseModel):
    results: list[ChannelResult]
    quota_used_session: int
    channels_scanned: int
    warnings: list[str] = []
