"""YouTube Analytics API (OAuth, лише читання): утримання, середній перегляд, країни — автоматично замість ручного читання Studio.
Одноразово: `python -m app.explainer.yt auth` (відкриється браузер, входите у свій Google-акаунт власника каналу й даєте дозвіл).
Далі: `python -m app.explainer.yt analytics` → дописує в storage/channel_log/studio.json (avg_view_s, avg_pct, views_28d, us_pct, кількість субскрайберів…) і криві утримання.
Файли ключів лежать у secrets/ (у .gitignore): client_secret.json (скачуєте з Google Cloud) і token.json (створюється після входу)."""
import json
import sys
from datetime import date, timedelta

from . import CHANNEL_ID
from .log import MAP, ROOT, STUDIO, _load, _save, studio_set

SECRETS = ROOT / "secrets"
CLIENT = SECRETS / "client_secret.json"
TOKEN = SECRETS / "token.json"
SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly", "https://www.googleapis.com/auth/youtube.readonly"]


def credentials(interactive: bool = False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN.write_text(creds.to_json(), encoding="utf-8")
        return creds
    if not interactive:
        raise RuntimeError("немає дійсного токена: виконайте `python -m app.explainer.yt auth`")
    if not CLIENT.exists():
        raise RuntimeError(f"немає {CLIENT}: скачайте OAuth-ключ (Desktop app) з Google Cloud і покладіть сюди")
    from google_auth_oauthlib.flow import InstalledAppFlow
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", authorization_prompt_message="Відкриваю браузер для входу в Google…")
    SECRETS.mkdir(parents=True, exist_ok=True)
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def auth() -> None:
    credentials(interactive=True)
    print("готово: токен збережено в", TOKEN)


def _svc(creds):
    from googleapiclient.discovery import build
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def pull(days: int = 90) -> dict:
    """Метрики по відео за останні `days` днів + країни + криві утримання; результат пишеться в studio.json."""
    creds = credentials()
    an = _svc(creds)
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=days)
    vmap = _load(MAP, {})
    rep = an.reports().query(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(), dimensions="video",
                             metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,likes,comments,subscribersGained",
                             sort="-views", maxResults=200).execute()
    n = 0
    for row in rep.get("rows", []):
        vid, views, mins, avg_s, avg_pct, likes, com, subs = row
        slug = vmap.get(vid)
        if not slug:
            continue
        studio_set(slug, views_api=int(views), avg_view_s=round(avg_s, 1), avg_pct=round(avg_pct, 1), likes_api=int(likes), subs_gained=int(subs))
        n += 1
    # країни (весь канал)
    cr = an.reports().query(ids="channel==MINE", startDate=start.isoformat(), endDate=end.isoformat(), dimensions="country", metrics="views", sort="-views", maxResults=10).execute()
    rows = cr.get("rows", [])
    tot = sum(r[1] for r in rows) or 1
    geo = {r[0]: round(100 * r[1] / tot, 1) for r in rows}
    d = _load(STUDIO, {})
    d["_channel"] = {"countries_pct": geo, "period": [start.isoformat(), end.isoformat()], "updated": date.today().isoformat()}
    _save(STUDIO, d)
    # криві утримання (тільки для відео з відомим slug; один виклик на відео)
    curves = 0
    for vid, slug in vmap.items():
        try:
            r = an.reports().query(ids="channel==MINE", startDate="2020-01-01", endDate=end.isoformat(), dimensions="elapsedVideoTimeRatio",
                                   metrics="audienceWatchRatio", filters=f"video=={vid}", sort="elapsedVideoTimeRatio").execute()
        except Exception:   # noqa: BLE001 — для нових відео звіт може бути порожній
            continue
        curve = [round(x[1], 3) for x in r.get("rows", [])]
        if curve:
            studio_set(slug, retention_curve=curve, ret_3s_pct=None)
            curves += 1
    return {"videos": n, "curves": curves, "countries": geo}


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "auth":
        auth()
    else:
        print(json.dumps(pull(), ensure_ascii=False, indent=1))
