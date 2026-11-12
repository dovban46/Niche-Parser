"""Повний цикл explainer-відео з відновленням (кожен крок кешується у робочій папці):
    python -m app.explainer.produce <slug> --topic "..." --step design|beats|voice|assets|render|package
Робоча папка: storage/explainer_jobs/<slug>/ ; видача: videos/<slug>/ (video.mp4, thumbnails, metadata.txt)."""
import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .. import audio_mix, chapters, music
from ..config import STORAGE_ROOT, VIDEOS_ROOT
from ..ffutil import error_tail, probe_duration, run_ffmpeg
from ..providers.llm.anthropic_provider import AnthropicLLMProvider
from . import assets, director, samples, tts
from .mix import plan_sfx
from .storyboard import actor_kwargs

NICHE = "заборонені тексти й легенди давнини (древні цивілізації)"
SECTION_GAP_S = 0.25
JOBS = STORAGE_ROOT / "explainer_jobs"
NL = chr(10)


def _wd(slug: str) -> Path:
    d = JOBS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _jload(p: Path):
    return json.load(open(p, encoding="utf-8"))


def _jsave(p: Path, data) -> None:
    json.dump(data, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------- 1. досьє + дизайн ----------
def step_design(slug: str, topic: str, n_sections: int, log=print, nbg: int = 14, nprops: int = 16, nactors: int = 4) -> dict:
    wd = _wd(slug)
    llm = AnthropicLLMProvider()
    dos = wd / "dossier.txt"
    if not dos.exists():
        log("досьє …")
        dos.write_text(llm.build_dossier(topic, NICHE), encoding="utf-8")
    out = wd / "design.json"
    if not out.exists():
        log("дизайн відео …")
        data = director.design(llm, topic, dos.read_text(encoding="utf-8"), n_sections, nbg=nbg, nprops=nprops, nactors=nactors, log=log, library=assets.library())
        data["topic"] = topic
        _jsave(out, data)
    return _jload(out)


def merged_catalog(design: dict) -> tuple[dict, dict, dict]:
    if design.get("fresh"):
        bgs = dict(design.get("backgrounds") or {})
        props = {k: (v["p"] if isinstance(v, dict) else v) for k, v in (design.get("props") or {}).items()}
    else:
        bgs = dict(samples.BACKGROUNDS)
        bgs.update(design.get("backgrounds") or {})
        props = dict(samples.PROPS)
        props.update(design.get("props") or {})
    actors = {"sage": {}, "you": samples.ACTORS["you"]}
    for k, v in (design.get("actors") or {}).items():
        if (k not in actors or k == "you") and isinstance(v, dict):   # «you» можна перевизначити (герой серії «Life as …»)
            actors[k] = v
    return bgs, props, actors


def prop_float(design: dict) -> list[str]:
    return [k for k, v in (design.get("props") or {}).items() if isinstance(v, dict) and v.get("float")]


# ---------- 2. біти ----------
def step_beats(slug: str, total_minutes: float, log=print) -> list[dict]:
    wd = _wd(slug)
    llm = AnthropicLLMProvider()
    design = _jload(wd / "design.json")
    dossier = (wd / "dossier.txt").read_text(encoding="utf-8")
    bgs, props, actors = merged_catalog(design)
    walk = {k: assets.analyze_bg(k)["walkable"] for k in bgs if (assets.ASSET_ROOT / "bg" / f"{assets._slug(k)}.png").exists()}
    catalog = director.catalog_text(bgs, props, actors, walk or None)
    n = len(design["sections"])
    words_total = total_minutes * 60 * director.WORDS_PER_SEC
    (wd / "sections").mkdir(exist_ok=True)
    all_beats: list[dict] = []
    warns: list[str] = []
    for i in range(n):
        f = wd / "sections" / f"{i:02d}.json"
        if not f.exists():
            log(f"розділ {i + 1}/{n}: {design['sections'][i]['title']} …")
            ff = wd / "factsheet.txt"
            facts = ff.read_text(encoding="utf-8") if ff.exists() else ""
            prev_text = " ".join(b["t"] for b in all_beats)
            raw = director.write_section(llm, design, i, catalog, dossier, all_beats[-6:], int(words_total / n), log, facts=facts, prev_text=prev_text)
            beats, w = director.sanitize(raw, bgs, props, actors)
            _jsave(f, {"beats": beats, "warnings": w})
        data = _jload(f)
        for b in data["beats"]:
            b["sec"] = i
        all_beats += data["beats"]
        warns += data["warnings"]
    words = sum(len(b["t"].split()) for b in all_beats)
    log(f"бітів {len(all_beats)}, слів {words} (≈{words / director.WORDS_PER_SEC / 60:.1f} хв), попереджень {len(warns)}")
    for w in warns[:15]:
        log("  ! " + w)
    _jsave(wd / "beats.json", all_beats)
    (wd / "script.txt").write_text(NL.join(
        f"## {design['sections'][i]['title']}{NL}" + " ".join(b["t"] for b in all_beats if b["sec"] == i) + NL for i in range(n)),
        encoding="utf-8")
    return all_beats


# ---------- 3. озвучка ----------
def step_voice(slug: str, voice_id: str | None = None, log=print) -> dict:
    wd = _wd(slug)
    beats = _jload(wd / "beats.json")
    design = _jload(wd / "design.json")
    n = len(design["sections"])
    (wd / "voice_parts").mkdir(exist_ok=True)
    texts = []
    for i in range(n):
        texts.append(" ".join(b["t"] for b in beats if b["sec"] == i))
    parts, durs, aligns = [], [], []
    for i in range(n):
        mp3, aj = wd / "voice_parts" / f"{i:02d}.mp3", wd / "voice_parts" / f"{i:02d}.json"
        if not (mp3.exists() and aj.exists()):
            log(f"озвучка розділу {i + 1}/{n} ({len(texts[i])} символів) …")
            al = tts.synthesize_with_timestamps(texts[i], mp3, voice_id, previous_text=texts[i - 1] if i else "",
                                                next_text=texts[i + 1] if i + 1 < n else "")
            _jsave(aj, al)
        parts.append(mp3)
        durs.append(probe_duration(mp3))
        aligns.append(_jload(aj))
    # склейка з паузою між розділами
    voice = wd / "voice.mp3"
    args = []
    for p in parts:
        args += ["-i", str(p)]
    # хук: прибираємо тишу перед першим словом (озвучка стартує з 0-го кадру); решта розділів — без змін
    first_words = tts.words_from_alignment(aligns[0])
    cut0 = max(0.0, (first_words[0]["s"] if first_words else 0.0) - 0.04)
    cuts = [cut0] + [0.0] * (n - 1)
    durs[0] = durs[0] - cut0
    fl = ";".join((f"[{i}:a]atrim=start={cuts[i]:.3f},asetpts=PTS-STARTPTS," if cuts[i] else f"[{i}:a]") + f"aresample=44100,apad=pad_dur={SECTION_GAP_S}[a{i}]"
                  for i in range(n))
    fl += ";" + "".join(f"[a{i}]" for i in range(n)) + f"concat=n={n}:v=0:a=1[o]"
    run_ffmpeg([*args, "-filter_complex", fl, "-map", "[o]", "-c:a", "libmp3lame", "-q:a", "2", str(voice)])
    total = probe_duration(voice)
    # таймінги бітів
    off = 0.0
    out_beats = []
    for i in range(n):
        words = tts.words_from_alignment(aligns[i])
        text = texts[i]
        pos = 0
        for b in [x for x in beats if x["sec"] == i]:
            i0 = text.index(b["t"], pos)
            i1 = i0 + len(b["t"])
            pos = i1
            ws = [w for w in words if w["i0"] >= i0 and w["i1"] <= i1 + 1]
            if not ws:
                raise RuntimeError(f"немає таймінгів для бітa: {b['t']}")
            c = dict(b)
            cut = cuts[i]
            c["s"], c["e"] = off + ws[0]["s"] - cut, off + ws[-1]["e"] - cut
            c["words"] = [{"w": w["w"], "s": off + w["s"] - cut, "e": off + w["e"] - cut} for w in ws]
            out_beats.append(c)
        off += durs[i] + SECTION_GAP_S
    bgs, props, actors = merged_catalog(design)
    used_bg = {b["bg"] for b in out_beats}
    used_props = {p[0] for b in out_beats for p in b.get("props", [])}
    sb = {"topic": design.get("topic"), "backgrounds": {k: v for k, v in bgs.items() if k in used_bg},
          "props": {k: v for k, v in props.items() if k in used_props}, "actors": actors,
          "format": design.get("format", "long"), "series": design.get("series", ""), "hud": design.get("hud", "inventory"), "meter_names": design.get("meter_names", {}), "style": design.get("style", {}), "grade": design.get("grade", ""), "music": design.get("music", 1),
          "prop_float": [k for k in prop_float(design) if k in used_props],
          "sections": [s["title"] for s in design["sections"]], "total": total, "beats": out_beats}
    _jsave(wd / "storyboard.json", sb)
    long_beats = [(round(b["e"] - b["s"], 1), b["t"]) for b in out_beats if b["e"] - b["s"] > 2.3]
    chars = sum(len(t) for t in texts)
    log(f"озвучка {total / 60:.1f} хв, {chars} символів, середній біт {sum(b['e'] - b['s'] for b in out_beats) / len(out_beats):.2f} с, довгих (>2.3 с): {len(long_beats)}")
    return sb


# ---------- 4. ресурси ----------
def step_assets(slug: str, log=print) -> None:
    """Фони й предмети (fal FLUX + суддя) + аналіз «прохідної» зони. До розкадрування — весь каталог дизайну; після — за сторібордом."""
    wd = _wd(slug)
    if (wd / "storyboard.json").exists():
        sb = _jload(wd / "storyboard.json")
        bgs, props = sb["backgrounds"], sb["props"]
    else:
        bgs, props, _ = merged_catalog(_jload(wd / "design.json"))
    jobs = [("bg", k, v) for k, v in bgs.items()] + [("prop", k, v) for k, v in props.items()]
    missing = [(t, k, v) for t, k, v in jobs if not (assets.ASSET_ROOT / t / f"{assets._slug(k)}.png").exists()]
    log(f"ресурси: потрібно {len(jobs)}, нових {len(missing)} (провайдер {assets.PROVIDER})")

    def gen(j):
        t, k, v = j
        try:
            (assets.ensure_bg if t == "bg" else assets.ensure_prop)(k, v, log=lambda *_: None)
            return None
        except Exception as exc:  # noqa: BLE001
            return f"{t} {k}: {exc}"
    with ThreadPoolExecutor(max_workers=4) as ex:
        errs = [e for e in ex.map(gen, missing) if e]
        for e in errs:
            log("  ! " + e)
        if errs:
            raise RuntimeError(f"не вдалось згенерувати {len(errs)} ресурсів (див. вище)")
        list(ex.map(lambda kv: assets.analyze_bg(kv[0], kv[1]), list(bgs.items())))
    walls = {k: assets.analyze_bg(k)["walkable"] for k in bgs}
    log("фони без ґрунту: " + (", ".join(k for k, w in walls.items() if not w) or "немає"))


# ---------- 5. рендер ----------
def step_render(slug: str, log=print) -> Path:
    from .render import render_parallel
    from .storyboard import load_timeline
    wd = _wd(slug)
    silent = wd / "silent.mp4"
    if not silent.exists():
        render_parallel(wd, silent, log=log)
    tl = load_timeline(wd)
    if getattr(tl, "is_short", False):
        from .mix import plan_sfx_short
        layers, info = plan_sfx_short(tl)
        bed = music.build_short_bed(tl.total, wd / "music_bed.m4a", variant=getattr(tl, "music_variant", 1))
        fade_in = 0.15
    else:
        layers, info = plan_sfx(tl)
        bed = music.build_bed(1, tl.total, wd / "music_bed.m4a")
        fade_in = 0.4   # хук: музика не «наїжджає» повільно, а є з перших секунд
    log(f"ефекти: {info}")
    if bed:
        layers.append(audio_mix.Layer(bed, 0.0, 0.0, length_s=tl.total, fade_in_s=fade_in, fade_out_s=2.5 if getattr(tl, "is_short", False) else 3.0, kind="music"))
    mix = wd / "mix.m4a"
    audio_mix.mix_soundtrack(wd / "voice.mp3", tl.total, layers, mix)
    out = wd / "video.mp4"
    try:
        run_ffmpeg(["-i", str(silent), "-i", str(mix), "-c:v", "copy", "-c:a", "copy", "-shortest", str(out)])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(error_tail(exc)) from exc
    log(f"відео: {out} ({probe_duration(out) / 60:.1f} хв)")
    return out


# ---------- 6. упаковка ----------
def step_package(slug: str, log=print) -> Path:
    from . import packaging, thumb
    wd = _wd(slug)
    sb = _jload(wd / "storyboard.json")
    llm = AnthropicLLMProvider()
    script = (wd / "script.txt").read_text(encoding="utf-8")
    meta_f = wd / "metadata.json"
    if not meta_f.exists():
        log("метадані …")
        header = ("[FORMAT: animated stickman-style EXPLAINER on a history channel. A wise old bearded sage narrates; the viewer is "
                  "addressed as 'you'. Titles/thumbnails should follow top explainer channels: curiosity gap, 'you' framing.]" + NL + NL)
        _jsave(meta_f, llm.generate_metadata(header + script, "en"))
    m = _jload(meta_f)
    pk_f = wd / "packages.json"
    if not pk_f.exists():
        log("пари прев'ю+назва …")
        _jsave(pk_f, packaging.build_packages(llm, script, sb, log))
    packages = _jload(pk_f)
    secs = {}
    for b in sb["beats"]:
        secs.setdefault(b["sec"], b["s"])
    ch = [(chapters._fmt(0.0 if i == 0 else secs[i]), t) for i, t in enumerate(sb["sections"])]
    desc = chapters.add_to_description(m["description"], ch)
    dest = VIDEOS_ROOT / slug
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(wd / "video.mp4", dest / "video.mp4")
    thumbs = thumb.make_from_packages(packages, sb, dest, log)
    lines = ["ПАРИ «ПРЕВ'Ю + НАЗВА» (читаються як одне речення; слова не повторюються)", "=" * 60]
    for i, pk in enumerate(packages[:3], 1):
        lines += [f"{i}. thumbnail_{i}.png — текст: {pk['thumb_text']}", f"   НАЗВА: {pk['title']}"]
        for alt in pk.get("alt_titles", []):
            lines.append(f"   альтернатива: {alt}")
        lines.append(f"   чому працює: {pk.get('why', '')}")
    lines += ["", "ОПИС", "=" * 4, desc, "", f"ТЕГИ ({len(chr(44).join(m['tags']))} із 500 символів)", "=" * 4, ", ".join(m["tags"])]
    if m.get("pinned_comment"):
        lines += ["", "ЗАКРІПЛЕНИЙ КОМЕНТАР", "=" * 4, m["pinned_comment"]]
    (dest / "metadata.txt").write_text(NL.join(lines), encoding="utf-8")
    (dest / "script.txt").write_text(script, encoding="utf-8")
    log(f"видача: {dest} (прев'ю: {len(thumbs)})")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--topic")
    ap.add_argument("--sections", type=int, default=6)
    ap.add_argument("--minutes", type=float, default=12.0)
    ap.add_argument("--voice")
    ap.add_argument("--new-bg", type=int, default=14)
    ap.add_argument("--new-props", type=int, default=16)
    ap.add_argument("--new-actors", type=int, default=4)
    ap.add_argument("--step", default="design")
    a = ap.parse_args()
    if a.step == "design":
        d = step_design(a.slug, a.topic, a.sections, nbg=a.new_bg, nprops=a.new_props, nactors=a.new_actors)
        print(json.dumps({k: d[k] for k in ("title_working", "hook")}, ensure_ascii=False, indent=1))
        for s in d["sections"]:
            print("-", s["title"])
        print("bg:", list((d.get("backgrounds") or {})), "props:", list((d.get("props") or {})), "actors:", list((d.get("actors") or {})))
    elif a.step == "beats":
        step_beats(a.slug, a.minutes)
    elif a.step == "voice":
        step_voice(a.slug, a.voice)
    elif a.step == "assets":
        step_assets(a.slug)
    elif a.step == "render":
        step_render(a.slug)
    elif a.step == "package":
        step_package(a.slug)


if __name__ == "__main__":
    main()
