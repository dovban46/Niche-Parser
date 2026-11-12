"""Генератор кадрів у Google Flow через Chrome з CDP (127.0.0.1:<порт з cdp.txt>, браузер за потреби запускається сам). Копія лежить у теці агента, запуск: python flow_runner.py

Правила (рішення користувача 2026-10-24):
- кожен файл генерується ОДИН раз: повторна генерація лише якщо Flow показав плитку-помилку (картинки не було), ніколи після таймауту;
- нова картинка розпізнається за новим src у сітці (сітка віртуалізована, кількість плиток не росте), а не за кількістю плиток;
- картинка зберігається одразу після появи: src плитки вже є оригіналом 1376x768, качаємо його з кукі браузера, без детального вигляду й меню 1K;
- короткі паузи: 1.5-3 с між генераціями, 0.3-0.8 с між кліками; після "unusual activity" паузи x1.5 на 10 кадрів;
- довга робота без нагляду: обрив зв'язку з браузером → пауза й повторне підключення (до MAX_RESTARTS разів), продовження з місця зупинки."""

import asyncio
import base64
import hashlib
import io
import json
import random
import re
import sys
import time
from pathlib import Path

from PIL import Image
from playwright.async_api import async_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PROMPTS = HERE / "prompts.json"
PROGRESS = OUT / "progress.json"
SRCMAP = OUT / "srcmap.json"          # data-media-id картинки -> файл (щоб жодну картинку не взяти двічі)
_port_file = Path(__file__).with_name("cdp.txt")      # порт Chrome цього агента (другий агент = інший Chrome/акаунт, напр. 9223)
PORT = int(_port_file.read_text().strip()) if _port_file.exists() else 9222
CDP = f"http://127.0.0.1:{PORT}"                     # саме 127.0.0.1: «localhost» інколи резолвиться в ::1, де Chrome не слухає
PROFILE_DIR = Path(r"C:\Users\volod\chrome-debug")    # профіль Chrome з уже виконаним входом у Flow (той самий, що в ручній команді користувача)
PER_PROJECT = 40                       # новий проєкт Flow після стількох генерацій
GEN_TIMEOUT = 120                      # с: чекати картинку; далі перезавантаження й перевірка, без повторної генерації
GAP = (1.5, 3.0)                       # пауза між генераціями
CLICK = (0.3, 0.8)                     # пауза між кліками
IMG_SEL = "flow-grid-tile-container img.image, flow-image-tile img.image"
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 0   # тест: зупинитись після N генерацій (0 = без ліміту)
ERR_WORDS = ("вичерпали ліміт", "usage limit", "unusual activity", "незвичн", "something went wrong", "щось пішло не так", "failed", "не вдалося")

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
OUT.mkdir(exist_ok=True)
class LimitHit(Exception):
    pass


class NeedLogin(Exception):
    pass


pace, pace_left = 1.0, 0
PASS = 0                               # номер проходу main(): з другого проходу заблоковані кадри йдуть з пом'якшеним промптом


def _alive() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(CDP + "/json/version", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


_DEAD_CHECKS = 0                       # скільки перевірок поспіль Chrome з профілем живий, а порт мертвий (завис)
_LOCK = None                           # сокет-замок: лише ОДИН flow_runner на порт Chrome (2026-11-06: 4 копії ламали одна одній вкладки)


def single_instance() -> bool:
    """Займає локальний порт 10000+PORT. Друга копія не зможе його зайняти й одразу вийде.
    Замок звільняється сам, коли процес завершується (навіть після закриття консолі чи вбивства)."""
    global _LOCK
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 10000 + PORT))
        s.listen(1)
    except OSError:
        s.close()
        return False
    _LOCK = s
    return True


def _profile_pids() -> list[int]:
    """PID процесів chrome.exe саме з цим профілем. wmic у Windows 11 видалено, тому PowerShell."""
    import subprocess
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process -Filter \"name = 'chrome.exe'\" | ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }"],
            capture_output=True, text=True, timeout=20).stdout
    except Exception:
        return []
    key = str(PROFILE_DIR).lower()
    return [int(l.split("\t", 1)[0]) for l in out.splitlines() if "\t" in l and key in l.lower() and l.split("\t", 1)[0].isdigit()]


def _profile_running() -> bool:
    """Чи працює вже Chrome з цим профілем (навіть без відкритого порту: тоді він блокує профіль)."""
    return bool(_profile_pids())


def ensure_browser():
    """Chrome з віддаленим налагодженням на порту з cdp.txt і профілем PROFILE_DIR (там уже є вхід у Flow).
    Те саме, що вручну: chrome.exe --remote-debugging-port=9222 --user-data-dir="C:/Users/volod/chrome-debug".
    Якщо Chrome з цим профілем завис (процес є, порт мовчить ~2 хв), скрипт закриває ЛИШЕ процеси цього профілю й запускає один новий."""
    global _DEAD_CHECKS
    if _alive():
        _DEAD_CHECKS = 0
        return True
    pids = _profile_pids()
    if pids:
        _DEAD_CHECKS += 1
        if _DEAD_CHECKS < 4:
            log(f"Chrome з профілем {PROFILE_DIR} працює, але порт {PORT} не відповідає ({_DEAD_CHECKS}/4); чекаю")
            return False
        import subprocess
        log(f"Chrome з профілем {PROFILE_DIR} завис: закриваю його процеси ({len(pids)}) і запускаю заново")
        subprocess.run(["taskkill", "/F", "/T"] + sum((["/PID", str(p)] for p in pids), []), capture_output=True, timeout=30)
        time.sleep(5)
        _DEAD_CHECKS = 0
        if _profile_pids():
            log("процеси Chrome цього профілю не закрились; спробую пізніше")
            return False
    import os
    import shutil
    import subprocess
    cands = [os.path.join(os.environ.get(k, ""), r"Google\Chrome\Application\chrome.exe") for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
    exe = next((c for c in cands if os.path.exists(c)), None) or shutil.which("chrome")
    if not exe:
        log("Chrome не знайдено: запустіть його вручну з --remote-debugging-port", PORT)
        return False
    log(f"запускаю Chrome: порт {PORT}, профіль {PROFILE_DIR}")
    try:
        subprocess.Popen([exe, f"--remote-debugging-port={PORT}", f"--user-data-dir={PROFILE_DIR}", "--remote-allow-origins=*", "--no-first-run",
                          "--no-default-browser-check", "https://flow.google.com/"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        log("не вдалося запустити Chrome:", e)
        return False
    for _ in range(40):
        time.sleep(1)
        if _alive():
            log("Chrome готовий")
            return True
    log("Chrome не відкрив порт", PORT)
    return False


RISKY = (("in terror", "wide-eyed"), ("with terror", "wide-eyed"), ("terrified", "startled"), ("terror", "fear"), ("screaming", "calling out"), ("scream", "call out"),
         ("reaching toward", "near"), ("reaching for", "near"), ("faceless", "pale blank-headed"), ("blood", "dark water"), ("corpse", "still figure"),
         ("dead body", "still figure"), ("coffin", "wooden box"), ("strangl", "grab"), ("kill", "stop"), ("horrified", "startled"), ("gore", "mess"))


def soften(prompt: str) -> str:
    """Пом'якшує сцену промпту, який Flow заблокував фільтром безпеки (лише частина після 'Scene:')."""
    head, sep, scene = prompt.partition("Scene:")
    low = scene
    for a_, b_ in RISKY:
        low = re.sub(a_, b_, low, flags=re.I)
    return head + sep + low + " Calm composition, dim light, no violence."


def log(*a):
    line = " ".join([time.strftime("%H:%M:%S")] + [str(x) for x in a])
    try:
        print(line, flush=True)
    except Exception:                    # без консолі (фоновий запуск в Antigravity) print дає OSError 22
        pass
    try:
        with open(OUT / "runner.log", "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


async def pause(rng):
    await asyncio.sleep(random.uniform(*rng) * pace)


def load(p, default):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def save(p, data):
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def md5(b: bytes) -> str:
    return hashlib.md5(b).hexdigest()


def existing_md5() -> dict:
    """MD5 усіх кадрів у out/ цього агента й сусідніх агентів (дублікати між агентами теж ловимо)."""
    res = {}
    for f in HERE.parent.glob("agent_*/out/*.jpg"):
        if f.stat().st_size > 10000:
            res[md5(f.read_bytes())] = f.name
    return res


class State:
    def __init__(self):
        p = load(PROGRESS, {})
        self.skipped = list(dict.fromkeys(p.get("skipped", [])))
        self.defects = p.get("defects", [])
        self.errors = p.get("errors", [])
        self.gens = 0
        self.t0 = time.time() - p.get("total_seconds", 0)
        self.srcmap = load(SRCMAP, {})
        self.why = p.get("skip_reason", {})     # файл -> error | submit | timeout | duplicate
        self.last_timeout = None                # файл, чия картинка могла запізнитись
        self.streak = 0                         # плиток-помилок поспіль (скидається успішним кадром)

    def write(self, items, last, note="", finished=False, blocked=None):
        done = sum(1 for it in items if (OUT / it["file"]).exists())
        d = {"done_items": done, "total_items": len(items), "last_item": last, "skipped": self.skipped,
             "defects": self.defects, "errors": self.errors[-60:], "notes": note, "finished": finished,
             "total_seconds": round(time.time() - self.t0, 1), "generations": self.gens,
             "skip_reason": {k: v for k, v in self.why.items() if k in self.skipped}}
        if blocked:
            d["blocked"], d["blocked_reason"] = True, blocked
        save(PROGRESS, d)
        save(SRCMAP, self.srcmap)


SRC_OF: dict[str, str] = {}               # ключ картинки -> її поточний src (для скачування)


async def grid_srcs(page) -> list[str]:
    """Ключі картинок сітки згори вниз (найновіша перша). Ключ = data-media-id (стабільний), а не src:
    Flow періодично переписує підписані src старих плиток, і стара картинка виглядала «новою» (v05: зсуви кадрів)."""
    pairs = await page.evaluate("""(sel) => {
        for (const e of document.querySelectorAll('*')) {
            if (e.scrollTop > 0 && e.scrollHeight > e.clientHeight) e.scrollTop = 0;
        }
        return Array.from(document.querySelectorAll(sel)).filter(i => i.naturalWidth > 300)
            .map(i => [i.dataset.mediaId || i.src, i.src]);
    }""", IMG_SEL)
    for key, src in pairs:
        SRC_OF[key] = src
    return [key for key, _ in pairs]


async def top_tile_text(page) -> str:
    return (await page.evaluate("""() => Array.from(document.querySelectorAll('flow-grid-tile-container')).slice(0, 2)
        .map(e => e.innerText || '').join(' | ')""")).lower()


async def check_hard_stop(page):
    if "accounts.google.com" in page.url:
        return "sign-in page"
    body = (await page.evaluate("() => document.body.innerText")).lower()
    for w, why in (("buy credits", "credits"), ("insufficient credits", "credits"), ("upgrade your plan", "upgrade"),
                   ("купити кредити", "credits"), ("account is suspended", "suspended"), ("account is blocked", "blocked"),
                   ("акаунт заблоковано", "blocked")):
        if w in body:
            return why
    return None


async def fetch_image(page, src: str) -> bytes:
    try:
        r = await page.context.request.get(src, timeout=30000)
        if r.ok:
            return await r.body()
    except Exception as e:
        log("request.get не вдалося:", e)
    b64 = await page.evaluate("""async (src) => {
        const r = await fetch(src, {credentials: 'include'});
        const b = new Uint8Array(await r.arrayBuffer());
        let s = ''; for (let i = 0; i < b.length; i += 32768) s += String.fromCharCode.apply(null, b.subarray(i, i + 32768));
        return btoa(s);
    }""", src)
    return base64.b64decode(b64)


def save_jpeg(raw: bytes, target: Path) -> tuple[int, int]:
    im = Image.open(io.BytesIO(raw))
    w, h = im.size
    if im.format == "JPEG":
        target.write_bytes(raw)
    else:
        im.convert("RGB").save(target, "JPEG", quality=95)
    return w, h


def white_border(path: Path) -> bool:
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        px = im.load()
        edges = [[px[x, 0] for x in range(w)], [px[x, h - 1] for x in range(w)], [px[0, y] for y in range(h)], [px[w - 1, y] for y in range(h)]]
        return any(sum(1 for p in e if min(p) > 248) / len(e) > 0.95 for e in edges)


async def dismiss_overlays(page):
    """Закриває вітальні діалоги Flow (напр. «Nano Banana 2.1 → Почати») і промо-картки, що перекривають кнопки."""
    for _ in range(3):
        try:
            hit = await page.evaluate("""() => {
                const dlg = document.querySelector('mat-dialog-container, [role=dialog], .cdk-overlay-pane');
                if (!dlg) return false;
                const ok = ['почати', 'get started', 'got it', 'continue', 'далі', 'next', 'ok', 'закрити', 'close', 'skip', 'пропустити', 'зрозуміло', 'done', 'start'];
                const bs = Array.from(dlg.querySelectorAll('button'));
                let b = bs.find(x => ok.includes((x.innerText || '').trim().toLowerCase())) || bs.find(x => /close|clear/.test(x.innerText || ''));
                if (b) { b.click(); return true; }
                return false;
            }""")
        except Exception:
            hit = False
        if not hit:
            break
        await asyncio.sleep(0.8)
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass


LOGIN_URL = "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fflow.google.com%2F"


async def wait_login(page, minutes: int = 20) -> bool:
    """Профіль цього Chrome не залогінений (Flow показує /about). Відкриває вхід Google у вікні скрипта, виводить вікно наперед
    і чекає, поки користувач увійде (нічого не вводить сам). True = вхід є, False = час вийшов."""
    if "accounts.google.com" not in page.url:
        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
    try:
        cdp = await page.context.new_cdp_session(page)
        win = await cdp.send("Browser.getWindowForTarget")
        await cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": {"windowState": "normal"}})
        await cdp.send("Browser.setWindowBounds", {"windowId": win["windowId"], "bounds": {"left": 60, "top": 40, "width": 1300, "height": 900}})
    except Exception:
        pass
    await page.bring_to_front()
    log(f"ПОТРІБЕН ВХІД: у вікні Chrome (профіль {PROFILE_DIR}) відкрита сторінка входу Google. Увійдіть тим акаунтом, де Flow; скрипт чекає до {minutes} хв")
    for _ in range(minutes * 12):
        await asyncio.sleep(5)
        u = page.url
        if "accounts.google.com" not in u and "/about" not in u and ("flow" in u or "labs.google" in u):
            log("вхід виконано, продовжую")
            await asyncio.sleep(3)
            return True
    return False


async def new_project(page, name: str) -> str:
    log(f"новий проєкт {name}")
    for attempt in range(4):
        await page.goto("https://flow.google.com/", wait_until="domcontentloaded")
        await asyncio.sleep(3)
        if "accounts.google.com" in page.url or "/about" in page.url:
            if not await wait_login(page):
                raise NeedLogin(page.url)
            continue
        await dismiss_overlays(page)
        try:
            btn = await page.wait_for_selector("button.new-project-button", timeout=25000)
            try:
                await btn.click(timeout=6000, force=True)             # промо-картка анімується: «стабільності» чекати не можна
            except Exception:
                await page.evaluate("() => document.querySelector('button.new-project-button').click()")
        except Exception as e:
            log(f"кнопка нового проєкту ({attempt + 1}/4): {type(e).__name__}")
            continue
        try:
            await page.wait_for_url("**/project/**", timeout=15000)
            break
        except Exception:
            log(f"проєкт не відкрився ({attempt + 1}/4), повтор")
    else:
        raise RuntimeError("не вдалося створити проєкт у Flow (див. out/last_error.png)")
    try:                                                              # поле назви є не в усіх акаунтах/версіях
        inp = await page.wait_for_selector("input.editable-text-input", timeout=4000)
        await inp.click()
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
        await inp.fill(name)
        await inp.press("Enter")
    except Exception:
        pass
    await page.wait_for_selector("flow-base-prompt-box .ProseMirror, .ProseMirror", timeout=30000)
    await dismiss_overlays(page)
    try:
        await check_settings(page)
    except Exception as e:
        log("налаштування x1 не змінено:", type(e).__name__)
    return page.url.split("/edit/")[0]


async def check_settings(page):
    """Модель Nano Banana 2.1 і один результат на промпт (x1). Профіль Chrome міг запам'ятати Nano Banana Pro:
    у нього окремий малий ліміт («Ви вичерпали ліміт використання»), а в 2.1 ліміту практично немає."""
    st = await page.query_selector(".settings-trigger-button")
    if not st:
        return
    await st.click(timeout=6000, force=True)
    await pause(CLICK)
    trig = await page.query_selector("flow-prompt-box-settings button.mat-mdc-menu-trigger")
    if trig and "2.1" not in (await trig.text_content() or ""):
        await trig.click(force=True, timeout=5000)
        await asyncio.sleep(0.8)
        item = await page.wait_for_selector("button.mat-mdc-menu-item:has-text('Nano Banana 2.1')", timeout=5000)
        await item.click(force=True, timeout=5000)
        await pause(CLICK)
    x1 = await page.query_selector("flow-prompt-box-settings button.mat-button-toggle-button:has-text('x1')")
    if x1 and (await x1.get_attribute("aria-checked")) != "true":
        await x1.click(force=True, timeout=5000)
        await pause(CLICK)
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.5)
    log("налаштування:", ((await st.text_content()) or "").replace(chr(10), " ").strip())


async def submit(page, prompt: str):
    await dismiss_overlays(page)
    pm = await page.wait_for_selector("flow-base-prompt-box .ProseMirror, .ProseMirror", timeout=20000)
    await pm.click()
    await pause(CLICK)
    await page.evaluate("""(text) => {
        const el = document.querySelector('flow-base-prompt-box .ProseMirror') || document.querySelector('.ProseMirror');
        el.focus();
        document.execCommand('selectAll', false, null);
        document.execCommand('delete', false, null);
        document.execCommand('insertText', false, text);
        el.dispatchEvent(new Event('input', {bubbles: true}));
    }""", prompt)
    await page.keyboard.press("Space")
    await page.keyboard.press("Backspace")
    await pause(CLICK)
    sel = "flow-base-prompt-box button.generate-icon-button:not([disabled]), button.generate-icon-button:not([disabled])"
    btn = await page.wait_for_selector(sel, timeout=10000)
    await btn.click()


async def click_retry(page) -> bool:
    for c in await page.query_selector_all("flow-grid-tile-container"):
        txt = (await c.inner_text()).lower()
        if any(w in txt for w in ERR_WORDS):
            b = await c.query_selector("button:has(mat-icon:has-text('refresh')), button[aria-label*='Retry'], button[aria-label*='retry'], button[aria-label*='Повторити']")
            if b:
                await b.click()
                return True
            return False
    return False


async def wait_new(page, seen: set, project_url: str, st: State, fname: str) -> str | None:
    """Чекає нову картинку після ОДНОГО натискання Generate. Повертає її src або None (без повторної генерації)."""
    global pace, pace_left
    retries, t0 = 0, time.time()
    while time.time() - t0 < GEN_TIMEOUT:
        await asyncio.sleep(0.5)
        new = [s for s in await grid_srcs(page) if s not in seen]
        if new:
            for extra in new[1:]:                       # запізніла картинка попереднього файлу (після його таймауту)
                late = st.last_timeout
                if late and not (OUT / late).exists():
                    log(f"{late}: запізніла картинка знайдена")
                    if await take(page, extra, OUT / late, seen, existing_md5(), st) and late in st.skipped:
                        st.skipped.remove(late)
                    st.last_timeout = None
                else:
                    seen.add(extra)
                    st.errors.append(f"{fname}: extra image ignored")
            return new[0]
        txt = await top_tile_text(page)
        if any(w in txt for w in ERR_WORDS):
            if "вичерпали ліміт" in txt or "usage limit" in txt:
                raise LimitHit(txt[:120])
            unusual = "unusual" in txt or "незвичн" in txt
            st.errors.append(f"{fname}: error tile ({'unusual activity' if unusual else 'error'}) #{retries + 1}")
            st.streak += 1
            if unusual:
                pace, pace_left = 1.5, 10
            if retries >= 2:
                st.why[fname] = "error"
                return None
            retries += 1
            await asyncio.sleep(2)
            if await click_retry(page):                 # повтор тієї самої (невдалої) плитки, нова картинка не створюється двічі
                log(f"{fname}: повтор плитки-помилки ({retries})")
                t0 = time.time()
                continue
            st.why[fname] = "error"
            return None
    # таймаут: перезавантажити й подивитись, чи картинка все ж з'явилась (НЕ генерувати вдруге)
    st.errors.append(f"{fname}: timeout {GEN_TIMEOUT}s")
    await page.goto(project_url, wait_until="domcontentloaded")
    for _ in range(20):
        await asyncio.sleep(1)
        new = [s for s in await grid_srcs(page) if s not in seen]
        if new:
            return new[0]
    st.why[fname] = "timeout"
    st.last_timeout = fname
    return None


async def take(page, src: str, target: Path, seen: set, md5s: dict, st: State) -> bool:
    """src тут = ключ картинки (data-media-id); справжня адреса береться з останнього сканування сітки."""
    seen.add(src)
    raw = await fetch_image(page, SRC_OF.get(src, src))
    h = md5(raw)
    if h in md5s:
        st.errors.append(f"{target.name}: duplicate of {md5s[h]}, not saved")
        log(f"{target.name}: ДУБЛІКАТ {md5s[h]}, не збережено")
        st.why[target.name] = "duplicate"
        return False
    w, hh = save_jpeg(raw, target)
    md5s[md5(target.read_bytes())] = target.name
    st.srcmap[src] = target.name
    st.streak = 0
    if white_border(target):
        st.defects.append(target.name)
    log(f"збережено {target.name} {w}x{hh}")
    return True


_WIN = None


async def open_window(browser, url: str):
    """ОДНА робоча вкладка: бере наявну вкладку Flow/Google (решту таких закриває), нову створює лише якщо їх немає.
    Раніше після кожного збою створювалось нове вікно, і десятки фонових вкладок вантажили процесор і пам'ять."""
    global _WIN
    if _WIN is not None and not _WIN.is_closed():
        try:
            await _WIN.evaluate("1")
            return _WIN
        except Exception:
            _WIN = None
    ctx = browser.contexts[0]
    mine = [p for p in ctx.pages if "flow.google" in p.url or "accounts.google" in p.url or "labs.google" in p.url]
    for extra in mine[1:]:
        try:
            await extra.close()
        except Exception:
            pass
    if mine:
        _WIN = mine[0]
        return _WIN
    _WIN = await ctx.new_page()
    await _WIN.goto(url, wait_until="domcontentloaded")
    return _WIN


async def run():
    global pace, pace_left
    data = load(PROMPTS, {})
    items, job = data["items"], data.get("job", HERE.name)
    st = State()
    md5s = existing_md5()
    todo = [it for it in items if not (OUT / it["file"]).exists()]
    log(f"{job}: усього {len(items)}, лишилось {len(todo)}")
    if not todo:
        st.write(items, items[-1]["id"], "all done", finished=True)
        log("finished", job.split("_")[-1])          # print без консолі = OSError 22 і вічний цикл після «лишилось 0»
        return "done"
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(CDP)
        page = await open_window(browser, "https://flow.google.com/")
        await page.bring_to_front()
        run_id, n_proj = time.strftime("%m%d%H%M"), 1          # унікальні назви проєктів при перезапуску
        project_url = await new_project(page, f"{job}_{run_id}_{n_proj}")
        in_project = 0
        seen = set(st.srcmap) | set(await grid_srcs(page))
        for rnd in (1, 2):
            queue = [it for it in items if not (OUT / it["file"]).exists()]
            if rnd == 1:     # таймаут/дублікат = генерація вже була: не повторювати (див. правила)
                queue = [it for it in queue if st.why.get(it["file"]) not in ("timeout", "duplicate")]
            else:            # 2-й прохід: лише файли, де картинки не було взагалі (плитка-помилка або Generate не натиснуто)
                queue = [it for it in queue if st.why.get(it["file"]) in ("error", "submit")]
                if queue:
                    log(f"повертаюсь до пропущених: {len(queue)}")
            for it in queue:
                target = OUT / it["file"]
                if target.exists():
                    continue
                if LIMIT and st.gens >= LIMIT:
                    log(f"ліміт тесту {LIMIT} генерацій")
                    st.write(items, it["id"], "test limit")
                    return "limit"
                stop = await check_hard_stop(page)
                if stop:
                    st.write(items, it["id"], f"STOP: {stop}", blocked=stop)
                    log("СТОП:", stop)
                    return "blocked"
                if in_project >= PER_PROJECT:
                    n_proj += 1
                    project_url = await new_project(page, f"{job}_{run_id}_{n_proj}")
                    in_project = 0
                    seen |= set(await grid_srcs(page))
                await pause(GAP)
                t = time.time()
                try:
                    await submit(page, soften(it["prompt"]) if (rnd == 2 or PASS > 1) and it["file"] in st.skipped else it["prompt"])
                except Exception as e:
                    st.errors.append(f"{it['file']}: submit failed {e}")
                    st.why[it["file"]] = "submit"
                    if it["file"] not in st.skipped:
                        st.skipped.append(it["file"])
                    log(f"{it['file']}: не вдалося надіслати ({e}), перезавантаження")
                    await page.goto(project_url, wait_until="domcontentloaded")
                    await asyncio.sleep(3)
                    continue                                 # Generate не натиснуто, тож у 2-му проході можна спробувати знову
                st.gens += 1
                in_project += 1
                src = await wait_new(page, seen, project_url, st, it["file"])
                ok = bool(src) and await take(page, src, target, seen, md5s, st)
                if ok:
                    st.why.pop(it["file"], None)
                    if it["file"] in st.skipped:
                        st.skipped.remove(it["file"])
                elif it["file"] not in st.skipped:
                    st.skipped.append(it["file"])
                if pace_left:
                    pace_left -= 1
                    if not pace_left:
                        pace = 1.0
                log(f"[{it['id']}] {it['file']} {'OK' if ok else 'ПРОПУСК'} за {time.time() - t:.0f} с")
                st.write(items, it["id"], f"item {it['id']}")
                if st.streak >= 3:                           # 3 помилки поспіль: пауза 3 хв, нове вікно браузера, новий проєкт (рішення користувача 2026-10-25)
                    log(f"{st.streak} помилки поспіль: пауза 3 хв, нове вікно браузера")
                    st.errors.append(f"{it['file']}: 3 errors in a row, pause 180 s + new window")
                    st.write(items, it["id"], "3 errors in a row: pause 3 min, new window")
                    await asyncio.sleep(180)
                    # НЕ закривати вкладку: якщо вона остання, Chrome по CDP не може відкрити нову ("Failed to open a new tab") і зависає
                    if page.is_closed():
                        page = await open_window(browser, "https://flow.google.com/")
                    else:
                        await page.goto("https://flow.google.com/", wait_until="domcontentloaded")
                    await page.bring_to_front()
                    n_proj += 1
                    project_url = await new_project(page, f"{job}_{run_id}_{n_proj}")
                    in_project = 0
                    seen |= set(await grid_srcs(page))
                    st.streak = 0
                    pace, pace_left = 1.5, 10
    done = all((OUT / it["file"]).exists() for it in items)
    st.write(items, items[-1]["id"], "done" if done else "finished with skipped files", finished=done)
    log(f"кінець: пропущено {len(st.skipped)}")
    if done:
        log("finished", job.split("_")[-1])          # print без консолі = OSError 22 і вічний цикл після «лишилось 0»
    return "done" if done else "skipped"


async def main():
    """Цикл без нагляду: НІКОЛИ не падає через браузер чи Flow. Закрили Chrome, помилка Flow, ліміт, сторінка входу, збій мережі:
    скрипт чекає, за потреби сам запускає Chrome, і продовжує з місця зупинки. Завершується лише коли всі кадри є або після 8 проходів без прогресу."""
    global PASS, _WIN
    fails, last_done, idle_passes = 0, -1, 0
    while True:
        if not ensure_browser():
            log("браузер недоступний, чекаю 30 с і пробую знову")
            await asyncio.sleep(30)
            continue
        PASS += 1
        try:
            res = await run()
            fails = 0
            log(f"результат проходу {PASS}: {res}")
            if res in ("done", "limit"):
                return
            done_now = sum(1 for it in load(PROMPTS, {}).get("items", []) if (OUT / it["file"]).exists())
            if res == "blocked":
                st = load(PROGRESS, {})
                why = st.get("blocked_reason", "")
                wait = 20 if "sign-in" in why else 1800 if why in ("credits", "upgrade") else 600
                log(f"Flow недоступний ({why}): чекаю {wait} с (увійдіть/перевірте акаунт у вікні Chrome), тоді продовжу сам")
                await asyncio.sleep(wait)
                continue
            idle_passes = idle_passes + 1 if done_now == last_done else 0
            last_done = done_now
            if idle_passes >= 8:
                log("8 проходів без нових кадрів: зупиняюсь, лишились пропущені (див. out/progress.json)")
                return
            log("є пропущені кадри: пауза 3 хв і новий прохід (заблоковані йдуть з пом'якшеним промптом)")
            await asyncio.sleep(180)
        except KeyboardInterrupt:
            raise
        except NeedLogin:
            log("Flow просить увійти: увійдіть у відкритому вікні Chrome (той самий акаунт Flow), скрипт чекає 20 с і перевіряє знову")
            await asyncio.sleep(20)
        except LimitHit as e:
            log(f"ліміт використання Flow ({e}): чекаю 20 хв і продовжую сам")
            await asyncio.sleep(1200)
        except BaseException as e:
            fails += 1
            st = State()
            st.errors.append(f"pass {PASS} fail {fails}: {type(e).__name__}: {str(e)[:160]}")
            save(PROGRESS, {**load(PROGRESS, {}), "errors": st.errors[-60:], "notes": f"recovering after error ({fails})"})
            wait = min(20 * fails, 300)
            log(f"збій: {type(e).__name__}: {str(e)[:200]}; чекаю {wait} с і продовжую (браузер за потреби перезапущу)")
            try:
                if _WIN is not None and not _WIN.is_closed():
                    await _WIN.screenshot(path=str(OUT / "last_error.png"))
            except BaseException:
                pass
            _WIN = None
            await asyncio.sleep(wait)


if __name__ == "__main__":
    if not single_instance():
        log(f"інший flow_runner уже працює з Chrome на порту {PORT}: ця копія виходить (дві копії ламають одна одній вкладки й ловлять «unusual activity»)")
        sys.exit(0)
    asyncio.run(main())
