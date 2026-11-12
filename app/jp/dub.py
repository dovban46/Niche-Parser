"""Переклад відео іншою мовою без платних сервісів: переклад тексту бітів (пише Claude у чаті) + озвучка edge-tts
(безкоштовні нейронні голоси Microsoft, слова з таймінгами) + той самий рендер зі своїми кадрами й глибиною.

    dub.make_job(src_slug, dst_slug, n_beats, paragraphs, beat_texts, chapters)   # підготувати роботу
    dub.synthesize(dst_slug, voice="uk-UA-OstapNeural")                            # озвучка + timeline.json
    render.render(dst_slug)                                                       # рендер як зазвичай
"""

import asyncio
import re
import shutil
import subprocess

import edge_tts

from ..ffutil import error_tail, probe_duration, run_ffmpeg
from . import core

TAIL_S = 0.9
GAP_S = 0.25
RATE = "+18%"


SPOKEN_RE = re.compile(r"(\S*?)\[([^\]]+)\](\S*)")
ACUTE = "́"
# вимова: слово (нижній регістр, без наголосу) → як подати нейронці (наголошена голосна — велика літера).
STRESS = {   # перевірено на слух (2026-10-23): наголос великою літерою звучить правильно, комбінований акут нейронка ігнорує
    "самураї": "самурАї", "самураїв": "самурАїв", "самураями": "самурАями", "самураям": "самурАям", "самурай": "самурАй",
}


def strip_spoken(text: str) -> str:
    """Показуваний текст: «1281[тисяча двісті вісімдесят першому]» → «1281»."""
    return SPOKEN_RE.sub(lambda m: m.group(1) + m.group(3), text)


def parse_items(sentence: str) -> list[tuple[str, list[str]]]:
    """Список (показуване слово, [вимовлені слова]) для речення з розмітою «ЦИФРИ[слова]»."""
    out, pos = [], 0
    for m in SPOKEN_RE.finditer(sentence):
        out += [(t, [t]) for t in sentence[pos:m.start()].split()]
        spoken = m.group(2).split()
        spoken[-1] += m.group(3)
        out.append((m.group(1) + m.group(3), spoken))
        pos = m.end()
    out += [(t, [t]) for t in sentence[pos:].split()]
    return out


def pronounce(token: str) -> str:
    core_w = re.sub(r"[^\w']", "", token).lower()
    rep = STRESS.get(core_w)
    if not rep:
        return token
    pre = re.match(r"^\W*", token).group(0)
    post = re.search(r"\W*$", token).group(0)
    return pre + rep + post


def make_job(src: str, dst: str, paragraphs: list[str], beat_texts: list[str], chapters: dict | None = None) -> None:
    """Беремо перші len(beat_texts) бітів роботи src: кадри, глибина, структура камер ті самі; текст бітів = переклад."""
    s, d = core.job_dir(src), core.job_dir(dst)
    beats = core.load_json(s / "beats.json")[:len(beat_texts)]
    for b, t in zip(beats, beat_texts):
        b["t"] = t
        b.pop("chapter", None)
    for i, name in (chapters or {}).items():
        beats[int(i)]["chapter"] = name
    got = [w for t in beat_texts for w in core.words_of(t)]
    want = [w for p in paragraphs for w in core.words_of(strip_spoken(p))]
    if got != want:
        raise RuntimeError(f"слова бітів і абзаців розходяться ({len(got)} vs {len(want)})")
    core.save_json(d / "beats.json", beats)
    (d / "script.txt").write_text("\n".join(paragraphs) + "\n", encoding="utf-8")
    (d / "frames").mkdir(exist_ok=True)
    (d / "depth").mkdir(exist_ok=True)
    for i in range(len(beats)):
        for p in core.frame_paths(s, i):
            shutil.copy2(p, d / "frames" / p.name)
        npy = s / "depth" / f"beat_{i:03d}.npy"
        if npy.exists():
            shutil.copy2(npy, d / "depth" / npy.name)


def prosody(sentence: str, k: int) -> dict:
    """Проста «акторська гра» для edge-tts без стилів: питання вище, окличні гучніші, короткі фрази повільніші й нижчі, дрібне чергування."""
    n = len(core.words_of(sentence))
    rate, pitch, vol = 16, 0, 0
    if sentence.rstrip().endswith("?"):
        pitch, rate = pitch + 9, rate + 4
    elif sentence.rstrip().endswith("!"):
        pitch, vol = pitch + 4, vol + 12
    if n <= 3:
        rate, pitch = rate - 12, pitch - 4
    elif n >= 16:
        rate += 4
    pitch += (2 if k % 2 else -1)
    return {"rate": f"{rate:+d}%", "pitch": f"{pitch:+d}Hz", "volume": f"{vol:+d}%"}


async def _speak(text: str, mp3, voice: str, pr: dict | None = None) -> list[dict]:
    pr = pr or {"rate": RATE, "pitch": "+0Hz", "volume": "+0%"}
    com = edge_tts.Communicate(text, voice, rate=pr["rate"], pitch=pr["pitch"], volume=pr["volume"], boundary="WordBoundary")
    words = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                words.append({"w": ch["text"], "s": ch["offset"] / 1e7, "e": (ch["offset"] + ch["duration"]) / 1e7})
    return words


def synthesize(slug: str, voice: str = "uk-UA-OstapNeural") -> dict:
    d = core.job_dir(slug)
    lines = [l.strip() for l in (d / "script.txt").read_text(encoding="utf-8").splitlines() if l.strip()]
    sents, para_end = [], []
    for l in lines:
        ss = [x.strip() for x in re.split(r"(?<=[.!?…])\s+", l) if x.strip()]
        sents += ss
        para_end += [False] * (len(ss) - 1) + [True]
    words_all, offset, part_files, gaps = [], 0.0, [], []
    for i, text in enumerate(sents):
        mp3 = d / f"voice_part_{i}.mp3"
        items = parse_items(text)
        spoken = [pronounce(t) for _, sp in items for t in sp]
        raw = asyncio.run(_speak(" ".join(spoken), mp3, voice, prosody(strip_spoken(text), i)))
        dur_tmp = probe_duration(mp3)
        if len(raw) != len(spoken):           # межі слів не збіглися: ділимо тривалість пропорційно довжині слів
            tot = sum(len(t) for t in spoken)
            raw, t0 = [], 0.0
            for t in spoken:
                dd = dur_tmp * len(t) / tot
                raw.append({"w": t, "s": t0, "e": t0 + dd})
                t0 += dd
        ws, k = [], 0
        for disp, sp in items:                # група вимовлених слів (число) → одне показуване слово
            ws.append({"w": disp, "s": raw[k]["s"], "e": raw[k + len(sp) - 1]["e"]})
            k += len(sp)
        dur = probe_duration(mp3)
        for w in ws:
            words_all.append({"w": w["w"], "s": w["s"] + offset, "e": w["e"] + offset})
        part_files.append(mp3)
        gap = GAP_S if para_end[i] else 0.14
        gaps.append(gap)
        offset += dur + gap
    mp3_all = d / "voice.mp3"
    inputs, filt = [], []
    for k, f in enumerate(part_files):
        inputs += ["-i", str(f)]
        filt.append(f"[{k}:a]aresample=44100,apad=pad_dur={gaps[k]}[a{k}]")
    graph = ";".join(filt) + ";" + "".join(f"[a{k}]" for k in range(len(part_files))) + f"concat=n={len(part_files)}:v=0:a=1[out]"
    graph_file = d / "voice_concat.txt"      # граф у файлі: при ~240 реченнях командний рядок перевищує ліміт Windows (WinError 206)
    graph_file.write_text(graph, encoding="utf-8")
    try:
        run_ffmpeg([*inputs, "-filter_complex_script", str(graph_file), "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "128k", str(mp3_all)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError("ffmpeg (склейка озвучки): " + error_tail(exc))
    beats = core.load_json(d / "beats.json")
    out_beats, k = [], 0
    for b in beats:
        n = len(core.words_of(b["t"]))
        out_beats.append({"first": k, "last": k + n - 1})
        k += n
    if k != len(words_all):
        raise RuntimeError(f"слів у бітах {k}, у озвучці {len(words_all)}")
    total = probe_duration(mp3_all) or words_all[-1]["e"]
    for i, ob in enumerate(out_beats):
        start = 0.0 if i == 0 else words_all[ob["first"]]["s"] - 0.02
        end = (words_all[out_beats[i + 1]["first"]]["s"] - 0.02) if i + 1 < len(out_beats) else words_all[-1]["e"] + TAIL_S
        ob["s"], ob["e"] = round(max(start, 0.0), 3), round(end, 3)
    starts, k = [], 0
    for l in lines:
        starts.append({"word": k, "t": round(words_all[k]["s"], 3), "text": strip_spoken(l)[:60]})
        k += len(core.words_of(strip_spoken(l)))
    data = {"words": [{"w": w["w"], "s": round(w["s"], 3), "e": round(w["e"], 3)} for w in words_all],
            "beats": out_beats, "voice_s": round(total, 3), "total_s": round(words_all[-1]["e"] + TAIL_S, 3),
            "chars_billed": 0, "lines": starts, "voice": voice}
    core.save_json(d / "timeline.json", data)
    return data
