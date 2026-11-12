import sys, os, json
sys.path.insert(0, r"E:\YouTube\parser")
from dotenv import dotenv_values
from app import niche_scan as ns, youtube_client as yt
from pathlib import Path
_v=dotenv_values(r"E:\YouTube\parser\.env")
KEYS=[_v[k] for k in ["YOUTUBE_API_KEY_4","YOUTUBE_API_KEY_3","YOUTUBE_API_KEY_2","YOUTUBE_API_KEY_1","YOUTUBE_API_KEY"] if _v.get(k)]
state={"i":0}
def use(i):
    os.environ["YOUTUBE_API_KEY"]=KEYS[i]; yt._client=None; state["i"]=i
use(0)
def run(grid,out,log=print):
    p=ns.SCAN_DIR/out; ns.SCAN_DIR.mkdir(parents=True,exist_ok=True)
    done=ns.load(p)
    seen={(d["niche"],d["keyword"],d["region"],d["language"],d["duration"],d["days"]) for d in done}
    for spec in grid:
        key=(spec["niche"],spec["keyword"],spec["region"],spec["language"],spec.get("duration","medium"),spec.get("days",120))
        if key in seen: continue
        while True:
            try:
                r=ns.scan_pair(**spec); break
            except yt.YouTubeApiError as e:
                if ("квот" in str(e).lower() or "429" in str(e) or "uota" in str(e)) and state["i"]<len(KEYS)-1:
                    use(state["i"]+1); log(f"-- ключ -> #{state['i']}"); continue
                log("СТОП",e); return done
        done.append(r); p.write_text(json.dumps(done,ensure_ascii=False),encoding="utf-8")
        m=r["metrics"]; log(f"k{state['i']} {spec['language']} {spec['keyword'][:32]:32} n{m.get('n_videos')} ch{m.get('n_channels')} med{m.get('median_views')} yg{m.get('young_channels')} br{m.get('breakout_channels')}")
    return done
