"""Ріже script (з рядками-заголовками '# ...') на фрагменти-біти ~3-7 слів. Пише job/script.txt (без заголовків), marked.txt, frags.txt."""
import re, sys
from pathlib import Path
slug = sys.argv[1]
src = Path(f"episodes/{slug}/script.txt").read_text(encoding="utf-8").splitlines()
job = Path(f"storage/jp_jobs/{slug}"); job.mkdir(parents=True, exist_ok=True)
CONJ = {"і","й","а","але","що","щоб","бо","коли","як","де","та","на","в","у","з","не","чи","поки","тому","це","його","їх"}
def split_sentence(s):
    words = s.split()
    if len(words) <= 7: return [words]
    parts, cur = [], []
    for w in words:
        cur.append(w)
        if w.endswith(",") or w.endswith(":") or w.endswith(";"):
            parts.append(cur); cur = []
    if cur: parts.append(cur)
    out, cur = [], []
    for p in parts:
        if cur and len(cur)+len(p) > 7:
            out.append(cur); cur = []
        cur += p
    if cur: out.append(cur)
    res = []
    for p in out:
        while len(p) > 8:
            k = len(p)//2
            best = min(range(max(3,k-2), min(len(p)-2,k+3)), key=lambda i:(0 if p[i].lower() in CONJ else 1, abs(i-k)))
            res.append(p[:best]); p = p[best:]
        res.append(p)
    # зливаємо коротенькі (<3 слів) із сусідом
    i = 0
    while i < len(res):
        if len(res[i]) < 3 and len(res) > 1:
            j = i+1 if i+1 < len(res) else i-1
            a, b = (i, j) if j > i else (j, i)
            res[a:b+1] = [res[a]+res[b]]; i = 0; continue
        i += 1
    return res
paras, marked, frags, ch = [], [], [], None
n = 0
for ln in src:
    if not ln.strip(): continue
    if ln.startswith("#"):
        ch = ln.lstrip("# ").strip(); frags.append(f"=== {ch}"); marked.append(ln); continue
    paras.append(ln.strip()); line_frags = []
    for s in re.split(r"(?<=[.?!])\s+", ln.strip()):
        line_frags += split_sentence(s)
    marked.append(" / ".join(" ".join(f) for f in line_frags))
    for f in line_frags:
        n += 1; frags.append(f"{n:03d} {' '.join(f)}")
(job/"script.txt").write_text("\n".join(paras)+"\n", encoding="utf-8")
Path(f"episodes/{slug}/marked.txt").write_text("\n".join(marked)+"\n", encoding="utf-8")
Path(f"episodes/{slug}/frags.txt").write_text("\n".join(frags)+"\n", encoding="utf-8")
print(n, "фрагментів,", sum(len(p.split()) for p in paras), "слів")
