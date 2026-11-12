"""Перевірка перед публікацією (вшита в lifeas --step ship): відео, структура, метадані, правила каналу, повторюваність стилю.
FAIL = не публікувати, WARN = перевір, OK = пройдено. Правила — з досвіду каналу (Studio 2026-10-16, фідбек користувача, офіційні довідки YouTube)."""
import json
import re
import subprocess
import sys

from .log import JOBS, VIDEOS, _load, ROOT

MIN_S = 40.0                 # вимога користувача: 40 с мінімум
TARGET_WORDS = (95, 120)     # ≈0,40-0,47 с/слово → 42-52 с
TEASERS = ("next video", "coming soon", "part two", "part 2", "follow for", "stay tuned", "next time", "in the next")
CTA_WORDS = ("subscribe", "like and", "hit the bell", "smash")
BAD_CLAIMS = ("almost died", "deadly", "saved countless", "broke an empire", "shocking truth", "you won't believe", "everything you know", "100% true")


def _probe(path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,codec_name,r_frame_rate:format=duration,size",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    j = json.loads(out or "{}")
    s = (j.get("streams") or [{}])[0]
    f = j.get("format", {})
    return {"w": s.get("width"), "h": s.get("height"), "codec": s.get("codec_name"), "dur": float(f.get("duration", 0) or 0), "size": int(f.get("size", 0) or 0)}


def _lufs(path) -> float | None:
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?\d+\.\d)\s+LUFS", r.stderr)
    return float(m[-1]) if m else None


def parse_metadata(text: str) -> dict:
    sec = {}
    cur = None
    for ln in text.splitlines():
        if re.fullmatch(r"[А-ЯІЇЄA-Z ’'()≤0-9]+", ln.strip()) and ln.strip() and not ln.startswith("="):
            cur = ln.strip()
            sec[cur] = []
        elif cur is not None and not ln.startswith("===="):
            sec[cur].append(ln)
    titles = re.findall(r"^\d\.\s+(.+?)\s+\(\d+\)\s*$", text, re.M)
    desc = "\n".join(next((v for k, v in sec.items() if k.startswith("ОПИС")), [])).strip()
    tags = "\n".join(next((v for k, v in sec.items() if k.startswith("ТЕГИ")), [])).strip()
    return {"titles": titles, "desc": desc, "tags": [t.strip() for t in tags.split(",") if t.strip()]}


def check(slug: str) -> list[tuple[str, str]]:
    res: list[tuple[str, str]] = []

    def add(level, msg):
        res.append((level, msg))

    vdir, job = VIDEOS / slug, JOBS / slug
    vp = vdir / "video.mp4"
    if not vp.exists():
        return [("FAIL", f"немає {vp}")]
    pr = _probe(vp)
    add("OK" if (pr["w"], pr["h"]) == (1080, 1920) else "FAIL", f"формат {pr['w']}x{pr['h']} (треба 1080x1920 вертикаль)")
    add("OK" if pr["dur"] >= MIN_S else "FAIL", f"тривалість {pr['dur']:.1f} с (мінімум {MIN_S:.0f} с — вимога користувача)")
    if pr["dur"] > 75:
        add("WARN", "понад 75 с: утримання зазвичай падає")
    add("OK" if pr["codec"] == "h264" else "WARN", f"кодек {pr['codec']}")
    add("OK" if pr["size"] < 200e6 else "WARN", f"розмір {pr['size'] / 1e6:.0f} МБ")
    lufs = _lufs(vp)
    if lufs is None:
        add("WARN", "гучність не виміряно")
    else:
        add("OK" if -16.5 <= lufs <= -12.0 else "WARN", f"гучність {lufs:.1f} LUFS (ціль -14 ± 2)")

    beats = _load(job / "beats.json", [])
    design = _load(job / "design.json", {})
    if beats:
        words = sum(len(str(b.get("t", "")).split()) for b in beats)
        add("OK" if TARGET_WORDS[0] <= words <= TARGET_WORDS[1] else "WARN", f"слів озвучки {words} (ціль {TARGET_WORDS[0]}-{TARGET_WORDS[1]})")
        b0 = beats[0]
        hook = b0.get("hook") or b0.get("big")
        add("OK" if hook else "WARN", "хук-текст на кадрі 0 " + ("є: «%s»" % str(hook).replace("|", " ") if hook else "немає (великий текст перші 1,5 с)"))
        if hook and len(str(hook).replace("|", " ").split()) > 6:
            add("WARN", "хук довший за 6 слів")
        last = str(beats[-1].get("t", "")).strip()
        add("OK" if last.endswith((".", "!", "?")) else "FAIL", f"фінал «{last}» " + ("завершений" if last.endswith((".", "!", "?")) else "ОБІРВАНИЙ (потрібне повне речення)"))
        add("OK" if isinstance(beats[-1].get("card"), dict) or beats[-1].get("stamp") else "WARN", "кінцева плашка/графіка " + ("є" if isinstance(beats[-1].get("card"), dict) or beats[-1].get("stamp") else "немає"))
        text = " ".join(str(b.get("t", "")) for b in beats).lower()
        bad = [w for w in TEASERS if w in text]
        add("FAIL" if bad else "OK", "анонси наступного відео: " + (", ".join(bad) if bad else "немає"))
        cta_v = [w for w in CTA_WORDS if w in text]
        add("FAIL" if cta_v else "OK", "заклик підписатись озвучено: " + (", ".join(cta_v) if cta_v else "ні (лише графіка)"))
        n_cta = sum(1 for b in beats if b.get("cta"))
        add("OK" if n_cta == 1 else "WARN", f"графічних CTA: {n_cta} (треба 1)")
        early_ink = [b.get("tr") for b in beats[:6] if b.get("tr") in ("ink", "iris", "wipe")]
        add("FAIL" if early_ink else "OK", "повільні/чорні переходи в перших 6 бітах: " + (",".join(early_ink) if early_ink else "немає"))
    else:
        add("WARN", "немає beats.json: структуру не перевірено")

    mp = vdir / "metadata.txt"
    if mp.exists():
        md = parse_metadata(mp.read_text(encoding="utf-8"))
        for t in md["titles"]:
            if len(t) > 70 or "#" in t:
                add("WARN", f"назва «{t}»: {len(t)} символів або з хештегом")
        add("OK" if md["titles"] else "WARN", f"назв {len(md['titles'])}")
        tags = re.findall(r"#\w+", md["desc"])
        add("OK" if 3 <= len(tags) <= 5 else "WARN", f"хештегів в описі {len(tags)} (3-5)")
        add("OK" if any(t.lower() == "#shorts" for t in tags) else "WARN", "#Shorts в описі")
        if re.search(r"\[[^\]]+\]|https?://|LINK", md["desc"]):
            add("FAIL", "в описі заглушка/посилання (на Shorts посилання не працюють)")
        else:
            add("OK", "в описі немає заглушок і посилань")
        low = (" ".join(md["titles"]) + " " + md["desc"]).lower()
        hit = [w for w in BAD_CLAIMS if w in low]
        add("FAIL" if hit else "OK", "перебільшення в метаданих: " + (", ".join(hit) if hit else "немає"))
        add("OK" if 5 <= len(md["tags"]) <= 12 else "WARN", f"тегів {len(md['tags'])} (5-12, короткі й релевантні)")
        if design.get("art") == "photo" or "photo" in str(design.get("topic_art", "")):
            add("OK" if "AI-generated" in md["desc"] else "WARN", "опис містить «AI-generated»")
            add("WARN", "ПРИ ЗАВАНТАЖЕННІ: «Змінений або синтетичний контент» = Так (реалістичні ШІ-зображення)")
    else:
        add("WARN", "немає metadata.txt")

    reg = _load(ROOT / "storage" / "style_registry.json", {})
    keys = list(reg)
    if slug in reg:
        i = keys.index(slug)
        prev = [reg[k] for k in keys[max(0, i - 3):i]]
        same = [p for p in prev if p.get("cta") == reg[slug].get("cta") and p.get("subs") == reg[slug].get("subs") and p.get("grade") == reg[slug].get("grade")]
        add("WARN" if same else "OK", "оформлення " + ("повторює одне з 3 попередніх" if same else "відрізняється від 3 попередніх"))
    add("OK", "налаштування завантаження: Загальнодоступне · Ні, не для дітей · мова EN-US · категорія «Освіта» · НЕ натискати «Додати все» в хештегах")
    return res


def finalize(slug: str) -> None:
    """Стиснути зібране відео в videos/<slug>/video.mp4 (h264 crf 24; crf 28 якщо понад 200 МБ), якщо воно ще важке або старіше за джерело."""
    src, dst = JOBS / slug / "video.mp4", VIDEOS / slug / "video.mp4"
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
        return
    crf = "28" if src.stat().st_size > 200e6 else "24"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-c:v", "libx264", "-crf", crf, "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "copy", "-movflags", "+faststart", str(dst)], check=True)


def main(slug: str) -> int:
    res = check(slug)
    icon = {"OK": "  ok ", "WARN": " WARN", "FAIL": " FAIL"}
    for lv, msg in res:
        print(f"{icon[lv]}  {msg}")
    fails = sum(1 for lv, _ in res if lv == "FAIL")
    warns = sum(1 for lv, _ in res if lv == "WARN")
    print(f"\nпідсумок {slug}: FAIL {fails}, WARN {warns} → " + ("НЕ ПУБЛІКУВАТИ" if fails else "можна публікувати"))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
