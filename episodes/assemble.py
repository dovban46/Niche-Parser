"""Збирає beats_src.txt: фрагмент || кадр || cast || cam з frags.txt + specs_*.txt. Запуск: python episodes/assemble.py <slug> [hook]"""
import re, sys, glob
from pathlib import Path
slug = sys.argv[1]
ep = Path(f"episodes/{slug}")
frags = {}
for ln in (ep / "frags.txt").read_text(encoding="utf-8").splitlines():
    m = re.match(r"^(\d{3}) (.*)$", ln)
    if m:
        frags[m.group(1)] = m.group(2).strip()
specs = {}
for f in sorted(glob.glob(str(ep / "specs_*.txt"))):
    for ln in Path(f).read_text(encoding="utf-8").splitlines():
        if ln.strip():
            p = [x.strip() for x in ln.split("||")]
            specs[p[0]] = p[1:]
miss = [k for k in frags if k not in specs]
extra = [k for k in specs if k not in frags]
if miss or extra:
    sys.exit(f"нема specs: {miss}; зайві: {extra}")
out = []
for k, t in frags.items():
    img, cast, cam = specs[k]
    if k == "001" and len(sys.argv) > 2:
        cam += (";" if " " in cam and not cam.endswith(" ") else " ") + "hook=" + sys.argv[2]
    out.append(f"{t} || {img} || {cast} || {cam}")
job = Path(f"storage/jp_jobs/{slug}"); job.mkdir(parents=True, exist_ok=True)
(job / "beats_src.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
print(len(out), "бітів")
