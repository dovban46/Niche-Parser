"""Звіт «що працює»: публічна статистика + дані Studio + параметри відео (набір стилів, довжина, слова, хук) в одній таблиці та короткі висновки."""
import re
import statistics

from .log import STUDIO, _load, job_info
from .tracker import latest


def dur_s(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    return int(m.group(1) or 0) * 60 + int(m.group(2) or 0) if m else 0


def build() -> list[dict]:
    studio = _load(STUDIO, {})
    rows = []
    for r in latest().values():
        slug = r.get("slug")
        info = job_info(slug) if slug else {}
        s = studio.get(slug, {}) if slug else {}
        rows.append({**info, "slug": slug or "?", "title": r["title"], "published": r["published"][:10], "views": r["views"], "likes": r["likes"],
                     "comments": r["comments"], "dur": dur_s(r["duration"]), "viewed_pct": s.get("viewed_pct"), "avg_view_s": s.get("avg_view_s"),
                     "avg_pct": s.get("avg_pct"), "swiped_pct": s.get("swiped_pct"), "curve": s.get("retention_curve")})
    rows.sort(key=lambda x: x["published"])
    return rows


def main() -> None:
    rows = [r for r in build() if r["slug"] != "?"]   # старі довгі відео FF без привʼязки до Shorts-пайплайна не рахуємо
    print(f"{'slug':26} {'дата':10} {'перегл':>6} {'лайк':>4} {'сек':>4} {'сер.пер.':>8} {'%':>5} {'слів':>4}  кіт / хук")
    for r in rows:
        print(f"{r['slug'][:26]:26} {r['published']:10} {r['views']:>6} {r['likes']:>4} {r['dur']:>4} {str(r.get('avg_view_s') or '-'):>8} {str(r.get('avg_pct') or '-'):>5} "
              f"{str(r.get('words') or '-'):>4}  {r.get('kit', '?')} / {(r.get('hook') or '')[:40]}")
    print("\nУТРИМАННЯ (частка глядачів, що ще дивляться): 10 % / 25 % / 50 % / 99 % тривалості")
    for r in rows:
        c = r.get("curve")
        if c:
            g = lambda p: c[min(len(c) - 1, int(p / 100 * len(c)))]
            print(f"  {r['slug'][:26]:26} {g(10):.2f} / {g(25):.2f} / {g(50):.2f} / {g(99):.2f}   обрив 10→25 %: {g(10) - g(25):.2f}")
    print("\nВИСНОВКИ")
    if len(rows) < 3:
        print("  замало відео")
        return
    long_, short_ = [r["views"] for r in rows if r["dur"] >= 40], [r["views"] for r in rows if r["dur"] < 40]
    if long_ and short_:
        print(f"  медіана переглядів: відео ≥40 с = {int(statistics.median(long_))}, <40 с = {int(statistics.median(short_))} (n={len(long_)}/{len(short_)})")
    by_kit: dict[str, list[int]] = {}
    for r in rows:
        by_kit.setdefault(r.get("kit", "?"), []).append(r["views"])
    for k, v in sorted(by_kit.items(), key=lambda kv: -statistics.median(kv[1])):
        print(f"  кіт {k:10} n={len(v)} медіана {int(statistics.median(v))}")
    pcts = [(r["avg_pct"], r["views"]) for r in rows if r.get("avg_pct")]
    if len(pcts) >= 4:
        hi = [v for p, v in pcts if p >= 45]
        lo = [v for p, v in pcts if p < 45]
        if hi and lo:
            print(f"  утримання ≥45 %: медіана {int(statistics.median(hi))} переглядів; <45 %: {int(statistics.median(lo))}")
    hi = [r for r in rows if r["views"] >= 800]
    lo = [r for r in rows if r["views"] < 400]
    print(f"  розподіл: ≥800 переглядів у {len(hi)} відео, <400 у {len(lo)} (двомодальний: або ~100, або ~1,1 тис. — тестові партії)")
    top = max(rows, key=lambda r: r["views"])
    print(f"  найкраще: {top['slug']} ({top['views']}), хук «{(top.get('hook') or '')[:50]}»")


if __name__ == "__main__":
    main()
