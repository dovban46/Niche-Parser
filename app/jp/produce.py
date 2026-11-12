"""Канал про Японію: CLI повного циклу тестового/звичайного відео.

    python -m app.jp.produce <slug> --step plan|images|voice|render|thumbs|ship|all

У теці storage/jp_jobs/<slug>/ мають лежати script.txt (вичитаний, факти перевірені: facts.txt) і metadata.json.
Кожен крок кешується; видалення файлу кроку перезапускає його."""

import argparse

from . import costs, gen, package, plan, render, thumbs, voice


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("slug")
    ap.add_argument("--step", default="all", choices=["plan", "images", "voice", "render", "thumbs", "ship", "all"])
    a = ap.parse_args()
    steps = ["plan", "images", "voice", "render", "thumbs", "ship"] if a.step == "all" else [a.step]
    costs.begin(a.slug)
    full = a.step == "all"
    if full:
        costs.snapshot(a.slug, "before")   # баланси ПЕРЕД генерацією
    for s in steps:
        print(f"== {s}")
        if s == "plan":
            plan.make(a.slug)
        elif s == "images":
            gen.images(a.slug)
            gen.rings(a.slug)
        elif s == "voice":
            voice.synthesize(a.slug)
        elif s == "render":
            render.render(a.slug)
        elif s == "thumbs":
            thumbs.make(a.slug)
        elif s == "ship":
            package.ship(a.slug)
    if full:
        costs.snapshot(a.slug, "after")    # баланси ПІСЛЯ і підсумок витрат
        costs.report(a.slug)


if __name__ == "__main__":
    main()
