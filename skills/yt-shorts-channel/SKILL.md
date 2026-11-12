---
name: yt-shorts-channel
description: Workflow, rules and tools for making and shipping YouTube Shorts for our US-audience channel (UC0aUH9P5HNpXccx-H_wtagA, series "TRUE NAVY STORIES" / military history): topic scan, script, style kits, render, pre-publish check, Studio analytics logging. Use for any request to make, review, package or analyse a Short for this channel.
---

# YouTube Shorts channel skill

Code lives in `E:\YouTube\video-factory` (branch `feature/explainer-format`), the topic scanner in `E:\YouTube\parser`. The user speaks Ukrainian; reply in Ukrainian, caveman-terse. Persisted text (metadata, memory, commits) in full sentences.

## Hard rules (from the user and from Studio data)
1. **Length 42-50 s (≥40 s minimum)**, about 95-115 words, **complete ending** (full closing sentence + end graphic). Never cut-off loop endings. Ask before testing shorter formats.
2. **Frame 0 = giant hook text** (`hook` beat field, ≤6 words, separator `|` for line breaks) + action; story runs forward; no black/ink/iris/wipe transitions in the first 6 beats.
3. **Never** voice a subscribe/like call; the CTA is a silent graphic (`cta: true` on exactly one calm beat at ~40-45 %). **Never** tease a next video. Links in Shorts descriptions are useless: no URLs, no placeholders.
4. **Facts must be real** (verify with Wikipedia via the `web-fetch` agent; hedge uncertain claims; reject popular legends the source rejects). Dramatising the telling is allowed; inventing is not. No gore.
5. **One niche** ("TRUE NAVY STORIES": US Navy / military history true stories and explainers). Studio showed topic hopping makes YouTube serve a random audience (Philippines 33 %, USA 5 %).
6. **Every video looks different**: new style combination vs the last 3 (`style_kit.pick` / presets POSTER, NAVAL, HERALDIC, DOSSIER, SERIOUS*, plus the cartoon axes). Keep characters, elements and editing varied; add something new each time.
7. Titles ≤70 chars, no hashtags in titles; description = hook line + one keyword sentence + 3-5 hashtags (`#Shorts` first); tags 5-12; no exaggeration words (deadly, almost died, saved countless…). Realistic AI imagery: description says "Images are AI-generated illustrations" and the upload sets **Altered or synthetic content = Yes**.
8. Never enter passwords; read Studio only while the user is logged in. Do not change Studio settings or edit public content without asking.

## Pipeline (video-factory)
```
python -m app.explainer.lifeas <slug> --role ... --facts facts.txt --cast <cast> --step hooks|plan|assets|voice|render|package|ship|all
EXPLAINER_ART=cartoon|serious|photo   # set for the assets step (photo = black-and-white documentary photos, serious = graphic novel)
```
Videos are usually built from a hand-written `scratchpad/sNN_build.py` (beats + design.json with `style`, `art`, `cast`, backgrounds, props), then `assets` → `voice` → `render` → `package` → `ship` (compress to `videos/<slug>/video.mp4` + checks).
Beat fields: `t` (narration, 2-9 words), `bg`, `who`, `pose`, `expr`, `shot`, `tr`, `props`, `big`, `hook`, `stamp`, `choice`, `counter`, `circle`, `meters`, `tilt`, `look` (nvg/thermal/oldfilm), `feed`, `cta`, and `card` = {type: dossier|split|route|timeline|stat|radar|photo|kinetic|deck}. Transitions: cut whip zoom flash slash ink glitch pixel push shutter tear sweep. Style presets in `app/explainer/style_kit.py`; cast in `casts.py`; run `python -m app.explainer.qa_chars <cast>` after touching characters (it also gates the render).

## Topic selection
`E:\YouTube\parser\app\niche_scan.py` (`run(grid, out_name)`, 10k quota/day, ~100 per query): scan US/en Shorts, 7-60 days, look at medians, breakouts and **young channels with few subscribers**. Winners so far: "why/how" naval and military explainers, WWII true stories (PolySoldier 437-717k), 5-s fact clips. Keep one scan file per day in `parser/app/data/scans/`.

## Analytics loop (the part that was missing)
```
python -m app.explainer.yt track            # public stats via Data API → storage/channel_log/snapshots.jsonl
python -m app.explainer.yt studio <slug> viewed_pct=34.1 swiped_pct=65.9 avg_view_s=17 avg_pct=37.8   # numbers only Studio shows
python -m app.explainer.yt report           # table views / retention / kit / hook + conclusions
python -m app.explainer.yt ship <slug>      # pre-publish check (FAIL = do not publish)
```
**Reading Studio** (built-in browser tools; the user must be logged in): `resize_window 1400x900` first (reset to `desktop` after); open `https://studio.youtube.com/channel/UC0aUH9P5HNpXccx-H_wtagA`; click "Перейти до аналітики каналу"; tabs Огляд / Контент / Аудиторія; read with `get_page_text`. Direct URLs work only as `/channel/<id>/analytics/tab-overview|tab-content|tab-build_audience/period-default` and `/video/<id>/analytics/tab-overview/period-default` (wait 5 s). Log per video: views, average view duration and % (Огляд → Найпопулярніший контент), viewed vs swiped away (Контент → Взаємодія глядачів), top countries (Аудиторія). Benchmarks to beat: viewed ≥70 %, avg view ≥60 % of length. Current: 32 % viewed, avg view 14-23 s, USA 5 % of views, 13 subscribers (2026-10-16).
Use `report` conclusions to pick the next topic/hook/kit; save findings in memory (`project_studio_shorts_*`).

## Findings from Analytics API (2026-10-17, 12 videos)
Retention is fine in the first ~10 % of a video (ratio about 1.0 or more) and **collapses between 10 % and 25 % of the length (seconds ~5-12): from ~1.0 to 0.35-0.64**. Best at 25 %: s08 trucker 0.64, s01 Jude 0.62, s04 Dracula 0.61, s09 carrier 0.56 (second-person threat / open question, rule or paradox right after the hook). Worst: s03, s10, s12, s06 (0.35): exposition, names, dates and definitions right after the hook. **Rule: put the second hook / reveal / visual shock at seconds 5-9, no setup or definitions there.** Views by country (28 d): Philippines 54 %, Ukraine 15 %, USA 8.7 %: the feed is not serving the US audience yet.
Run `python -m app.explainer.yt analytics` (OAuth is set up: secrets/client_secret.json + token.json, refresh token may expire after 7 days while the Google app is in Testing mode, then re-run `yt auth`) and `yt report` after every upload.

## Before every upload
Run `ship`, then follow `E:\YouTube\video-factory\UPLOAD_CHECKLIST.md`.

## Optional external skill
TubeAlfred YouTube plugin (claude.ai directory, community, read-only API: skills youtube-shorts, youtube-seo-audit, youtube-channel-audit, youtube-competitor, youtube-hashtag, youtube-keyword-ideas, youtube-comments). The user installs it from the plugin card; if `ListPlugins` shows it enabled, use it for competitor audits and keyword ideas, but treat its output as third-party data to verify.
