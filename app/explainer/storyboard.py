"""Збережене розкадрування (storyboard.json) → Timeline. Усе, що потрібно рендереру, лежить в одному файлі."""
import json
from pathlib import Path

from ..ffutil import probe_duration
from .render import FPS, Library, Timeline, mouth_levels

_TUPLE_FIELDS = ("skin", "hair", "beard", "robe", "trim", "brows", "hat_color", "mask_color", "mustache", "cape", "legs", "boots", "steel", "eye_color", "glove")


def actor_kwargs(raw: dict) -> dict:
    out = {}
    for k, v in (raw or {}).items():
        out[k] = tuple(v) if k in _TUPLE_FIELDS and isinstance(v, list) else v
    return out


def load_timeline(folder: Path) -> Timeline:
    sb = json.load(open(folder / "storyboard.json", encoding="utf-8"))
    actors = {k: actor_kwargs(v) for k, v in sb["actors"].items()}
    lib = Library(sb["backgrounds"].keys(), sb["props"].keys(), actors, sb.get("prop_float", []))
    total = sb["total"]
    mouths = mouth_levels(folder / "voice.mp3", int((total + 1) * FPS))
    if sb.get("format") == "short":
        from .render_short import ShortTimeline
        tl = ShortTimeline(sb["beats"], total, lib, mouths)
        tl.series_title = sb.get("series", "")
        tl.hud_mode = sb.get("hud", "inventory")
        tl.meter_names = sb.get("meter_names", {})
        tl.apply_style(sb.get("style", {}))
        tl.grade = sb.get("grade", "")
        tl.music_variant = int(sb.get("music", 1))
        return tl
    return Timeline(sb["beats"], total, lib, mouths)
