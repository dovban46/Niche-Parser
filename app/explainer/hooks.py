"""Фабрика гачків для Shorts: перші 1-2 секунди вирішують усе. Замість «першої ідеї» — генеруємо 10 гачків за різними формулами,
суворо відсікаємо те, чого нема у фактичному листі, оцінюємо за рубрикою «зупиняє скрол» і беремо найкращий.
Правила гачка (враховані в промптах): ≤7 слів, твердження (не привітання), конкретика (ім'я/число/предмет), відкрита петля,
видима картинка на 0-му кадрі, озвучка стартує з 0.0 с, великий текст на першому кадрі, звуковий удар на 0-му кадрі."""
from ..providers.llm.anthropic_provider import AnthropicLLMProvider, _extract_json

NL = chr(10)

_GEN = """You are a world-class Shorts hook writer. Write 10 DIFFERENT hook lines (first spoken sentence) for a 40-second animated Short. Each uses a different formula:
 1 CONTRADICTION ("Everything you know about X is wrong" — but concrete)
 2 YOU-THREAT (second person POV, immediate stakes: "You're hired to ...")
 3 NUMBER SHOCK (a specific number or date that does not fit)
 4 IRONY / TWIST (the thing meant to protect you did the opposite)
 5 HIDDEN REASON (the real reason behind something familiar)
 6 TIMELINE GAP ("270 years too late")
 7 FORBIDDEN / SECRET-LIKE but TRUE
 8 DIRECT ORDER / DARE to the viewer ("Don't ...", "Stop scrolling ...")
 9 QUESTION with instant stakes (only if the answer is withheld)
 10 COLD OPEN IN THE MIDDLE OF ACTION ("Day one. Nobody else wants this job.")
HARD RULES: <=5 words (the shorter the better, one breath, under 1.5 s); a viewer-directed THREAT or PARADOX, not information; the frame0 must be ACTION or CONFLICT (never a calm portrait, never a landscape); no past-tense narration of a rewound story; must be fully supported by the FACT SHEET (no invention); starts with the strongest word; NO filler openers (So, Today, Welcome, Did you know, In this video, Let's);
speakable in under 2.2 seconds; must be paired with a picture that shows it at frame 0.
Output ONLY JSON: [{"text": "...", "formula": 1-10, "frame0": "what the first frame shows (one sentence)", "big": "<=3 words CAPS for the on-screen text"}]"""

_JUDGE = """You judge Shorts hooks. For EACH hook give integer scores 0-10:
 stop = would it stop a bored thumb in <1 s (surprise, tension, personal stakes)
 spec = concrete and specific (names, numbers, objects) rather than generic
 loop = creates an open question the viewer must stay to answer
 true = fully supported by the fact sheet (0 if not supported or exaggerated)
 say = natural to say aloud in <1.5 s, punchy rhythm (6+ words: max 4)
 pic = easy to show as a striking first frame
total = stop*3 + loop*2 + spec*1.5 + say + pic + (true*3). Disqualify (total 0) when true<8.
Output ONLY JSON: [{"i": index, "stop": n, "spec": n, "loop": n, "true": n, "say": n, "pic": n, "total": n, "note": "<10 words"}]"""


def _call(llm: AnthropicLLMProvider, system: str, user: str, tokens: int = 4000):
    for _ in range(3):
        try:
            return _extract_json(llm._complete(system, user, tokens, effort="medium"))
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError("hooks: LLM не дав JSON")


def best_hooks(llm: AnthropicLLMProvider, topic: str, facts: str, log=print, top: int = 3) -> list[dict]:
    hooks = _call(llm, _GEN, f"TOPIC: {topic}{NL}{NL}FACT SHEET:{NL}{facts}")
    hooks = [h for h in hooks if isinstance(h, dict) and h.get("text") and len(h["text"].split()) <= 6]
    listing = NL.join(f"{i}: {h['text']}   [frame0: {h.get('frame0', '')}]" for i, h in enumerate(hooks))
    scores = _call(llm, _JUDGE, f"FACT SHEET:{NL}{facts}{NL}{NL}HOOKS:{NL}{listing}")
    by_i = {int(s["i"]): s for s in scores if isinstance(s, dict) and "i" in s}
    ranked = []
    for i, h in enumerate(hooks):
        sc = by_i.get(i, {})
        ranked.append({**h, "score": sc, "total": float(sc.get("total", 0))})
    ranked.sort(key=lambda x: -x["total"])
    for h in ranked[:top]:
        log(f"  {h['total']:5.1f}  {h['text']}   | {h['score'].get('note', '')}")
    return ranked
