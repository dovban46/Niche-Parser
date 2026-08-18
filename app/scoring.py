"""Розрахунок метрик каналу та фільтрація/скоринг "перспективних" каналів.

Ідея: канал цікавий, якщо у нього хороші перегляди на відео, І при цьому
він або новий (малий вік), або має мало відео (тобто "вистрілив" швидко,
органічно, а не за рахунок довгої історії каналу).
"""

from datetime import datetime, timezone

from .schemas import ChannelResult, SearchRequest


def _age_months(published_at: str | None) -> float | None:
    if not published_at:
        return None
    try:
        created = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = datetime.now(timezone.utc) - created
    return round(delta.days / 30.44, 1)


def build_channel_result(
    channel_id: str,
    raw: dict,
    matched_keywords: list[str],
    top_video: dict | None,
) -> ChannelResult:
    video_count = raw["video_count"]
    total_views = raw["view_count"]
    subs = raw["subscriber_count"]
    age = _age_months(raw.get("published_at"))

    views_per_video = round(total_views / video_count, 1) if video_count else 0.0
    views_per_sub = round(total_views / subs, 2) if subs else None

    # Евристичний score для сортування "гарячих" ніш:
    # більше переглядів на відео + менше відео (концентрація успіху) + новіший канал = вище.
    freshness = 12 / max(age, 1) if age is not None else 1.0
    concentration = views_per_video / max(video_count, 1)
    score = round(concentration * freshness / 100, 2)

    return ChannelResult(
        channel_id=channel_id,
        title=raw.get("title") or channel_id,
        url=f"https://www.youtube.com/channel/{channel_id}",
        country=raw.get("country"),
        created_at=raw.get("published_at"),
        age_months=age,
        video_count=video_count,
        subscriber_count=subs,
        total_view_count=total_views,
        views_per_video=views_per_video,
        views_per_subscriber=views_per_sub,
        score=score,
        matched_keywords=matched_keywords,
        top_video_title=top_video.get("title") if top_video else None,
        top_video_views=top_video.get("views") if top_video else None,
        top_video_url=(f"https://www.youtube.com/watch?v={top_video['video_id']}" if top_video else None),
    )


def passes_filters(channel: ChannelResult, req: SearchRequest) -> bool:
    if channel.views_per_video < req.min_views_per_video:
        return False

    is_small = channel.video_count <= req.max_video_count
    is_new = channel.age_months is not None and channel.age_months <= req.max_channel_age_months
    if not (is_small or is_new):
        return False

    if req.min_subscribers is not None and channel.subscriber_count < req.min_subscribers:
        return False
    if req.max_subscribers is not None and channel.subscriber_count > req.max_subscribers:
        return False

    return True
