"""Flow-конвеєр кадрів: експорт промптів для агентів Antigravity (Google Flow, Nano Banana), імпорт готових кадрів, статус.

Кадр біта: beat_{i:03d}.jpg (статичний кадр або якір анімації); додаткові пози анімації: beat_{i:03d}_2.jpg, _3, _4.
Агент створює позу редагуванням ЯКОРЯ (не попередньої пози), тож дрейфу між кадрами групи немає."""

import shutil
from pathlib import Path

from . import core, plan

ROOT = Path(r"E:\YouTube\Antigravity generator img")
FLOW_STYLE = (
    "Bright flat 2D vector cartoon for a food-explainer channel: thick dark outlines, flat color fills, clean shapes, no gradients, no paper texture; "
    "cheerful limited palette of tomato red, mustard yellow, mint green, sky blue and cream on a simple flat pastel or white background; "
    "very simple characters with plain round faces (two dot eyes, tiny mouth), round heads, tube-like limbs and rounded mitten hands without individual fingers; "
    "ONE clear main subject (a food item, an object or one character) drawn large in the center or on one third of the frame, plenty of empty space around it, "
    "medium shot, at most three main elements, simple background that fits the scene; {era}"
    "no text, no letters, no numbers, no logos, no signature, no border, no frame."
)
EDIT_PREFIX = ("Use the reference image exactly. Keep the character, clothes, colors, background, camera and style identical. "
               "Change only this: ")
ROLES = ("A", "B", "C")


def fname(i: int, k: int = 1) -> str:
    return f"beat_{i:03d}.jpg" if k == 1 else f"beat_{i:03d}_{k}.jpg"


def build_items(slug: str) -> list[dict]:
    beats = core.load_json(core.job_dir(slug) / "beats.json")
    cast = plan.load_cast(slug)
    era_f = core.job_dir(slug) / "era.txt"     # епоха відео (необов'язково), напр. "early 18th century (Edo period)"
    style = FLOW_STYLE.format(era=(era_f.read_text(encoding="utf-8").strip() + "; ") if era_f.exists() else "")
    faces_f = core.job_dir(slug) / "faces.txt"   # необов'язково: інший опис облич (з v18: велика міміка, як у хітів ніші)
    if faces_f.exists():
        style = style.replace("very simple characters with plain round faces (two dot eyes, tiny mouth)", faces_f.read_text(encoding="utf-8").strip())
    look_f = core.job_dir(slug) / "look.txt"   # необов'язково (2026-11-10): настрій/світло саме цього відео, стиль той самий
    if look_f.exists():
        style = style.replace("no text, no letters", look_f.read_text(encoding="utf-8").strip() + "; no text, no letters", 1)
    items = []
    for i, b in enumerate(beats):
        keys = [k for k in b.get("cast", []) if k in cast]
        looks = (" Character looks (draw exactly): " + "; ".join(f"{k} = {cast[k]}" for k in keys) + ".") if keys else ""
        it = {"id": i, "file": fname(i), "prompt": f"{style}{looks} Scene: {b['img']}", "edits": []}
        an = b.get("anim")
        if an:
            for k, pose in enumerate(an["poses"], start=2):
                pose = pose.split("but:", 1)[-1].strip()
                it["edits"].append({"file": fname(i, k), "text": EDIT_PREFIX + pose})
        items.append(it)
    return items


_INSTR = """# Agent {role}: pictures for the video "{slug}" in Google Flow

Your job: run the ready-made script `flow_runner.py` in this folder and keep it running until it is done.
Do NOT generate pictures by hand and do NOT write your own generator script.

## Rules
- Work only inside this folder: `{folder}`. You are the only agent: one script makes every picture of the video. It runs for hours; the user leaves it unattended.
- The script uses ONE Chrome with remote debugging (port from `cdp.txt`, profile C:/Users/volod/chrome-debug, already signed in to Flow). If that Chrome is not running, the script starts it once by itself; it never starts more copies and works in ONE tab. You do NOT open any browser. If the script prints "ПОТРІБЕН ВХІД" or that the profile is busy, tell the user and wait. Never enter passwords or codes yourself.
- Images only, never video, never anything that costs credits or asks for payment.

## Run
1. Open a terminal in this folder and run: `python flow_runner.py`
2. The script opens its OWN browser window, creates a new Flow project (a new one every 40 pictures) and for every item in `prompts.json`:
   pastes the prompt, presses Generate ONCE, waits for the new picture and saves it IMMEDIATELY as `out/<file>`
   (taken straight from the page, original 1376x768, no detail view, no Download menu). Pauses are short (1.5-3 s between pictures).
3. It resumes by itself: files already in `out/` are never generated again, and if the browser connection drops it waits and reconnects on its own (it gives up only on a sign-in page, credits, a blocked account, or after 30 failed reconnects). Progress is in `out/progress.json`.
4. Keep the script's window visible (not minimized). Do not touch other windows or tabs.
5. Every finished picture prints a line like `[130] beat_130.jpg OK за 23 с`.

## What must never happen (keep these rules even if you fix something)
- Never press Generate twice for one file. A second generation is allowed ONLY when Flow shows an error tile (no picture was made); the script does this itself.
- After a timeout the script does NOT generate again: it reloads the project and takes the late picture if it appears; otherwise the file stays in `skipped` with reason `timeout`. Leave it and report it.
- Never download through the detail view or the Download menu, never copy one picture to several names, never save a picture under a name that is not its own.

## If nothing happens (windows open but no pictures)
- Do NOT open windows or browser tabs yourself and do NOT start a second copy of the script.
- Read `out/progress.json` (field `errors`) and look at `out/last_error.png` (screenshot the script saves on every failure). Report both to the user in plain words.
- The script already closes Flow's welcome dialogs, clicks "New project" even when a promo card is animating, and reuses ONE window after a failure. If it still fails to create a project 3 times in a row, STOP and report; do not keep restarting.

## If the script stops
- The script is built to NEVER give up: if the browser is closed it starts Chrome again, if Flow shows errors or a limit it waits and retries, if Flow asks to sign in it waits for the user. So just keep it running and watch its output.
- Only if the process itself exits with a Python error (a traceback), start it again with `python flow_runner.py` (it resumes). If it prints that it stopped after 8 passes without new pictures, report the `skipped` list from `out/progress.json` and finish.
- Blocked pictures (Flow safety filter) are retried automatically with a softened prompt in the next pass.

## Done
When the script ends, read `out/progress.json` and report: `done_items`, `skipped` with `skip_reason`, `defects`, `total_seconds`.
Then say "finished {role}".
"""


_START = r"""# {slug}: кадри через Flow ({n} кадрів, один агент A)

## Як це працює
1. Chrome для Flow один: порт з `agent_A\cdp.txt` (9222) і профіль `C:\Users\volod\chrome-debug`, де вже є вхід у Flow. Це те саме, що ручна команда
   `chrome.exe --remote-debugging-port=9222 --user-data-dir="C:\Users\volod\chrome-debug"`.
2. Якщо такий Chrome уже відкритий (вручну або раніше), скрипт просто підключається до нього. Якщо ні, скрипт запускає його ОДИН раз сам.
3. Скрипт працює в ОДНІЙ вкладці Flow (зайві закриває), нові вікна в циклі не відкриває.
4. Якщо в профілі немає входу, скрипт відкриває вхід Google у цій вкладці й пише в лог «ПОТРІБЕН ВХІД»: увійдіть там один раз.
5. Якщо профіль зайнятий завислим Chrome (порт не відповідає), скрипт нічого не запускає і пише про це: закрийте всі вікна Chrome з цим профілем
   (або в PowerShell: `Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" | ? CommandLine -like '*chrome-debug*' | % {{ Stop-Process -Id $_.ProcessId -Force }}`) і запустіть агента знову.
6. Помилки Flow: ліміт = чекає 20 хв; 3 помилки поспіль = пауза 3 хв; заблокований фільтром кадр = наступний прохід з пом'якшеним промптом. Лог: `agent_A\out\runner.log`.
Зупиняється, коли всі кадри є (друкує `finished A`).

## Промпт для агента (відкрити `{base}` в Antigravity)
Запусти `python flow_runner.py` у теці agent_A (команда: `cd agent_A` і `python flow_runner.py`) і лиши його працювати до кінця. Не відкривай браузер і не генеруй картинки вручну: скрипт сам запускає Chrome і сам відновлюється після помилок Flow та закриття браузера. Якщо у вікні Chrome з'явиться вхід у Google, не вводь нічого сам: напиши мені, що потрібен вхід, а скрипт далі чекатиме. Якщо процес скрипта завершився з Python-помилкою (traceback), запусти його знову (він продовжує з місця зупинки). Не відкривай нових вікон. Коли скрипт надрукує "finished A", надішли мені дані з agent_A/out/progress.json.

(Тест на 2 кадри: `python flow_runner.py 2`.)

## Після «finished A»
Claude: `flow.status`, листи «кадр ↔ промпт», імпорт, глибина, рендер, прев'ю (концепти на вибір), метадані, видача.
"""


def export(slug: str, log=print, parts: dict | None = None) -> Path:
    """parts: {роль: [id, ...]}; за замовчуванням один агент A робить усі кадри (рішення 2026-10-24: користувач лишає його надовго)."""
    items = build_items(slug)
    if parts is None:
        parts = {"A": [x["id"] for x in items]}
    by_id = {x["id"]: x for x in items}
    base = ROOT / slug
    roles = list(parts)
    for role in roles:
        part = [by_id[i] for i in parts[role]]
        folder = base / f"agent_{role}"
        (folder / "out").mkdir(parents=True, exist_ok=True)
        shutil.copy2(Path(__file__).with_name("flow_runner.py"), folder / "flow_runner.py")
        if not (folder / "cdp.txt").exists():
            (folder / "cdp.txt").write_text(str(9222 + roles.index(role)), encoding="utf-8")   # свій Chrome-порт на агента
        core.save_json(folder / "prompts.json", {"job": f"{slug}_{role}", "aspect": "16:9", "items": part})
        n_files = sum(1 + len(x["edits"]) for x in part)
        (folder / "INSTRUCTIONS.md").write_text(
            _INSTR.format(role=role, slug=slug, folder=str(folder), n_items=len(part), n_files=n_files), encoding="utf-8")
        log(f"агент {role}: {len(part)} елементів, {n_files} кадрів → {folder}")
    (base / "START_HERE.md").write_text(_START.format(slug=slug, n=len(items), base=str(base)), encoding="utf-8")
    return base


def expected_files(slug: str) -> list[str]:
    out = []
    for it in build_items(slug):
        out.append(it["file"])
        out += [e["file"] for e in it["edits"]]
    return out


def status(slug: str) -> dict:
    base = ROOT / slug
    have = {p.name for r in ROLES for p in (base / f"agent_{r}" / "out").glob("beat_*.jpg")}
    want = expected_files(slug)
    missing = [f for f in want if f not in have]
    return {"want": len(want), "have": len(have & set(want)), "missing": missing}


def import_frames(slug: str, log=print) -> list[str]:
    """Копіює кадри агентів у frames/ роботи; повертає список відсутніх."""
    base = ROOT / slug
    dst = core.job_dir(slug) / "frames"
    dst.mkdir(exist_ok=True)
    for r in ROLES:
        for p in (base / f"agent_{r}" / "out").glob("beat_*.jpg"):
            shutil.copy2(p, dst / p.name)
    missing = [f for f in expected_files(slug) if not (dst / f).exists()]
    log(f"імпорт: відсутніх кадрів {len(missing)}")
    return missing
