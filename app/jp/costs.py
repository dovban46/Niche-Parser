"""Облік витрат і балансів по сервісах (fal, ElevenLabs, Anthropic, Google) для каналу про Японію.

Фактичні витрати рахуємо самі: кожен платний виклик пишеться в storage/jp_jobs/<slug>/costs.jsonl за прайсом
(fal: за прайс-листом, ElevenLabs: символи × ставка, Anthropic: токени × ціна). Це ОЦІНКА за публічними цінами:
реальне списання видно лише в дашбордах сервісів.

Баланси: пробуємо API; ключі, яким не дозволено читати білінг, дають 401/403, тоді береться останнє значення,
яке вписано вручну (`python -m app.jp.costs set fal 12.34 USD`), або явно «невідомо».

CLI:  python -m app.jp.costs check            # баланси зараз
      python -m app.jp.costs set <service> <value> <unit>
      python -m app.jp.costs report <slug>    # витрати прогону
"""

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

import requests

from .. import config  # noqa: F401  (підвантажує .env)
from ..config import STORAGE_ROOT

JOBS_ROOT = STORAGE_ROOT / "jp_jobs"
MANUAL = JOBS_ROOT / "balances_manual.json"
SERVICES = ["fal", "elevenlabs", "anthropic", "google"]

# ціни fal ($): за мегапіксель (FLUX) або за зображення (Nano Banana)
FAL_PER_MP = {"fal-ai/flux/schnell": 0.003, "fal-ai/flux/dev": 0.025}
FAL_PER_IMAGE = {"fal-ai/nano-banana/edit": 0.039, "fal-ai/nano-banana": 0.039}
ELEVEN_USD_PER_1K = float(os.environ.get("ELEVENLABS_USD_PER_1K_CHARS") or 0.20)   # оцінка за тарифом «Creator»; змінити під свій план
ANTHROPIC_PER_M = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-sonnet-5": (2.0, 10.0), "claude-opus-5": (5.0, 25.0), "claude-haiku-5-5": (0.1, 0.5), "claude-haiku-4-5": (1.0, 5.0)}

_lock = threading.Lock()
_slug: str | None = None
_llm_hooked = False


def begin(slug: str) -> None:
    """Вмикає облік для job'а й гачок на виклики Anthropic."""
    global _slug, _llm_hooked
    _slug = slug
    if not _llm_hooked:
        from ..providers.llm import usage
        original = usage.usage_tracker.record

        def hooked(model: str, input_tokens: int, output_tokens: int) -> None:
            original(model, input_tokens, output_tokens)
            spend_llm(model, input_tokens, output_tokens)

        usage.usage_tracker.record = hooked
        _llm_hooked = True


def spend(service: str, item: str, qty: float, usd: float, note: str = "") -> None:
    if not _slug:
        return
    d = JOBS_ROOT / _slug
    d.mkdir(parents=True, exist_ok=True)
    row = {"at": datetime.now().isoformat(timespec="seconds"), "service": service, "item": item, "qty": qty, "usd": round(usd, 5), "note": note}
    with _lock, (d / "costs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def spend_fal(model: str, size: tuple[int, int] | None = None) -> None:
    if model in FAL_PER_IMAGE:
        usd = FAL_PER_IMAGE[model]
    else:
        mp = (size[0] * size[1] / 1e6) if size else 1.0
        usd = FAL_PER_MP.get(model, 0.01) * mp
    spend("fal", model, 1, usd)


def spend_llm(model: str, tin: int, tout: int) -> None:
    key = next((k for k in ANTHROPIC_PER_M if model.startswith(k)), "claude-sonnet-5")
    pin, pout = ANTHROPIC_PER_M[key]
    spend("anthropic", model, tin + tout, (tin * pin + tout * pout) / 1e6, f"in {tin} / out {tout} токенів")


def spend_eleven(chars: int) -> None:
    spend("elevenlabs", "tts chars", chars, chars / 1000 * ELEVEN_USD_PER_1K, f"оцінка ${ELEVEN_USD_PER_1K}/1k символів")


# ---------------- баланси ----------------
def _manual() -> dict:
    return json.loads(MANUAL.read_text(encoding="utf-8")) if MANUAL.exists() else {}


def set_manual(service: str, value: float, unit: str) -> None:
    JOBS_ROOT.mkdir(parents=True, exist_ok=True)
    data = _manual()
    data[service] = {"value": value, "unit": unit, "at": datetime.now().isoformat(timespec="minutes")}
    MANUAL.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def _api_fal() -> tuple[float | None, str, str]:
    key = os.environ.get("FAL_API_KEY")
    if not key:
        return None, "USD", "нема FAL_API_KEY"
    r = requests.get("https://rest.alpha.fal.ai/billing/user_balance", headers={"Authorization": f"Key {key}"}, timeout=30)
    if r.status_code == 200:
        try:
            return float(r.json() if not isinstance(r.json(), dict) else next(iter(r.json().values()))), "USD", "api"
        except (ValueError, StopIteration, TypeError):
            return None, "USD", f"незрозуміла відповідь {r.text[:80]}"
    return None, "USD", f"API {r.status_code}: ключу бракує права billing:usage:read"


def _api_eleven() -> tuple[float | None, str, str]:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        return None, "символів", "нема ELEVENLABS_API_KEY"
    r = requests.get("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key": key}, timeout=30)
    if r.status_code == 200:
        j = r.json()
        return float(j["character_limit"] - j["character_count"]), "символів", "api"
    return None, "символів", f"API {r.status_code}: ключу бракує права user_read"


def check() -> dict:
    manual = _manual()
    out = {}
    for s in SERVICES:
        val, unit, note = None, "", ""
        try:
            if s == "fal":
                val, unit, note = _api_fal()
            elif s == "elevenlabs":
                val, unit, note = _api_eleven()
            elif s == "anthropic":
                unit, note = "USD", "API балансу кредитів не існує (лише Admin API зі звітом витрат)"
            elif s == "google":
                unit, note = "USD", "ключ Google не підключено до цього каналу" if not os.environ.get("GOOGLE_API_KEY") else "балансу через Gemini API нема (білінг у Cloud Console)"
        except requests.RequestException as exc:
            note = f"мережева помилка: {exc}"
        source = "api" if val is not None else "none"
        if val is None and s in manual:
            m = manual[s]
            val, unit, source, note = m["value"], m["unit"], "manual", f"вручну {m['at']}"
        out[s] = {"value": val, "unit": unit, "source": source, "note": note}
    return out


def print_balances(title: str, data: dict) -> None:
    print(f"--- {title}")
    for s in SERVICES:
        b = data[s]
        v = f"{b['value']:g} {b['unit']}" if b["value"] is not None else "невідомо"
        print(f"  {s:11} {v:>22}   [{b['source']}] {b['note']}")


def snapshot(slug: str, label: str) -> dict:
    data = check()
    d = JOBS_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    f = d / "balances.json"
    allb = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    allb[label] = {"at": datetime.now().isoformat(timespec="seconds"), "data": data}
    f.write_text(json.dumps(allb, ensure_ascii=False, indent=1), encoding="utf-8")
    print_balances(f"баланси: {label}", data)
    return data


def report(slug: str) -> dict:
    f = JOBS_ROOT / slug / "costs.jsonl"
    rows = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()] if f.exists() else []
    by: dict[str, dict] = {s: {"usd": 0.0, "n": 0} for s in SERVICES}
    for r in rows:
        b = by.setdefault(r["service"], {"usd": 0.0, "n": 0})
        b["usd"] += r["usd"]
        b["n"] += 1
    total = sum(b["usd"] for b in by.values())
    print(f"--- витрати прогону {slug} (оцінка за публічними цінами)")
    for s, b in by.items():
        print(f"  {s:11} ${b['usd']:.3f}   викликів {b['n']}")
    print(f"  {'РАЗОМ':11} ${total:.3f}")
    bf = JOBS_ROOT / slug / "balances.json"
    if bf.exists():
        allb = json.loads(bf.read_text(encoding="utf-8"))
        if "before" in allb and "after" in allb:
            print("--- різниця балансів до/після (де баланс відомий)")
            for s in SERVICES:
                a, z = allb["before"]["data"][s], allb["after"]["data"][s]
                if a["value"] is not None and z["value"] is not None:
                    print(f"  {s:11} {a['value']:g} → {z['value']:g} {a['unit']}  (списано {a['value'] - z['value']:g})")
                else:
                    print(f"  {s:11} баланс невідомий: порівняти нема з чим")
    return {"by_service": by, "total_usd": round(total, 4)}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        print_balances("баланси зараз", check())
    elif cmd == "set":
        set_manual(sys.argv[2], float(sys.argv[3]), sys.argv[4] if len(sys.argv) > 4 else "USD")
        print_balances("баланси зараз", check())
    elif cmd == "report":
        report(sys.argv[2])
