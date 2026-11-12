"""python -m app.explainer.make_voice <папка> [voice_id] — озвучка тестового розкадрування з таймінгами."""
import json
import sys
from pathlib import Path

from ..ffutil import probe_duration
from . import samples, tts


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    voice = sys.argv[2] if len(sys.argv) > 2 else None
    beats = samples.BEATS
    text, spans = "", []
    for b in beats:
        i0 = len(text) + (1 if text else 0)
        text = (text + " " + b["t"]) if text else b["t"]
        spans.append((i0, len(text)))
    al = tts.synthesize_with_timestamps(text, out / "voice.mp3", voice)
    words = tts.words_from_alignment(al)
    # межі бітів з таймінгів слів
    for b, (i0, i1) in zip(beats, spans):
        ws = [w for w in words if w["i0"] >= i0 and w["i1"] <= i1 + 1]
        b["s"], b["e"] = ws[0]["s"], ws[-1]["e"]
        b["words"] = [{"w": w["w"], "s": w["s"], "e": w["e"]} for w in ws]
    total = probe_duration(out / "voice.mp3")
    json.dump({"text": text, "total": total, "beats": beats}, open(out / "timing.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    wps = len(words) / max(total, 1)
    print(f"озвучка {total:.1f} с, {len(words)} слів ({wps:.2f} сл/с), символів {len(text)}")
    over = [(b["t"], round(b["e"] - b["s"], 2)) for b in beats if b["e"] - b["s"] > 2.0]
    print("біти довші за 2 с:", over)


if __name__ == "__main__":
    main()
