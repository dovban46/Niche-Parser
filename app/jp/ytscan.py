"""Безкоштовний скан попиту: пошукова видача YouTube, відсортована за переглядами (парсинг ytInitialData, без API й кредитів).

python -m app.jp.ytscan month "feudal japan" "edo period"      (період: week | month | year)"""

import json
import re
import sys
import urllib.parse

import requests

SP = {"week": "CAMSBAgDEAE%3D", "month": "CAMSBAgEEAE%3D", "year": "CAMSBAgFEAE%3D"}   # сортування за переглядами + період + лише відео
HEADERS = {"User-Agent": "Mozilla/5.0", "Accept-Language": "en-US,en;q=0.9", "Cookie": "CONSENT=YES+1"}


def search(q: str, period: str = "month") -> list[dict]:
    url = f"https://www.youtube.com/results?search_query={urllib.parse.quote(q)}&sp={SP[period]}&gl=US&hl=en"
    html = requests.get(url, headers=HEADERS, timeout=20).text
    data = json.loads(re.search(r"var ytInitialData = (\{.*?\});</script>", html).group(1))
    out = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("videoRenderer")
            if v:
                vc = v.get("viewCountText", {})
                vc = vc.get("simpleText") or "".join(r["text"] for r in vc.get("runs", []))
                out.append({"id": v["videoId"], "views": int(re.sub(r"\D", "", vc or "") or 0),
                            "age": v.get("publishedTimeText", {}).get("simpleText", ""),
                            "len": v.get("lengthText", {}).get("simpleText", ""),
                            "channel": v["ownerText"]["runs"][0]["text"], "title": v["title"]["runs"][0]["text"],
                            "thumb": f"https://i.ytimg.com/vi/{v['videoId']}/maxresdefault.jpg"})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(data)
    return sorted(out, key=lambda r: -r["views"])


def related(video_id: str) -> list[dict]:
    """Схожі відео праворуч від ролика (те, що YouTube рекомендує поруч), US-видача."""
    html = requests.get(f"https://www.youtube.com/watch?v={video_id}&gl=US&hl=en", headers=HEADERS, timeout=20).text
    data = json.loads(re.search(r"var ytInitialData = (\{.*?\});</script>", html).group(1))
    out = []

    def walk(o):
        if isinstance(o, dict):
            v = o.get("lockupViewModel")
            if v and v.get("contentType") == "LOCKUP_CONTENT_TYPE_VIDEO":
                md = v.get("metadata", {}).get("lockupMetadataViewModel", {})
                rows = md.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
                raw = [p for r in rows for p in r.get("metadataParts", [])]
                parts = [p.get("text", {}).get("content", "") for p in raw]
                n = next((p.get("text", {}).get("content", "") for p in raw if "view" in p.get("accessibilityLabel", "")), "")
                n = re.sub(r"[^0-9.KMB]", "", n)
                mul = {"K": 1e3, "M": 1e6, "B": 1e9}.get(n[-1:], 1) if n else 1
                num = int(float(n.rstrip("KMB") or 0) * mul) if n else 0
                out.append({"id": v.get("contentId"), "title": md.get("title", {}).get("content", ""),
                            "channel": parts[0] if parts else "", "views": num,
                            "age": next((x for x in parts if "ago" in x), "")})
            for x in o.values():
                walk(x)
        elif isinstance(o, list):
            for x in o:
                walk(x)

    walk(data.get("contents", {}).get("twoColumnWatchNextResults", {}).get("secondaryResults", {}))
    return out


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    period = sys.argv[1]
    for q in sys.argv[2:]:
        print("##", q)
        for r in search(q, period)[:10]:
            print(f"{r['views']:>11,} | {r['age']:14} | {r['len']:7} | {r['channel'][:22]:22} | {r['title'][:90]}")
