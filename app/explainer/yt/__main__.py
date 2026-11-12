import sys

USAGE = """python -m app.explainer.yt track                      знімок публічної статистики каналу (Data API) у журнал
python -m app.explainer.yt report                     таблиця «що працює» + висновки
python -m app.explainer.yt ship <slug>                перевірка перед публікацією (FAIL/WARN/OK)
python -m app.explainer.yt auth                       одноразовий вхід Google (OAuth, лише читання аналітики)
python -m app.explainer.yt analytics                  автоматично: утримання, середній перегляд, країни, криві → журнал
python -m app.explainer.yt studio <slug> k=v ...      внести метрики зі Studio: viewed_pct, swiped_pct, avg_view_s, avg_pct, views_28d, us_pct, ph_pct"""


def main() -> int:
    a = sys.argv[1:]
    if not a:
        print(USAGE)
        return 0
    if a[0] == "track":
        from .tracker import snapshot
        rows = snapshot()
        print(f"знімок: {len(rows)} відео, сума переглядів {sum(r['views'] for r in rows)}")
    elif a[0] == "report":
        from .report import main as rep
        rep()
    elif a[0] == "ship":
        from .ship_check import main as ship
        return ship(a[1])
    elif a[0] == "auth":
        from .analytics import auth
        auth()
    elif a[0] == "analytics":
        from .analytics import pull
        import json
        print(json.dumps(pull(), ensure_ascii=False, indent=1))
    elif a[0] == "studio":
        from .log import studio_set
        kv = {}
        for p in a[2:]:
            k, v = p.split("=", 1)
            kv[k] = float(v) if v.replace(".", "", 1).replace("-", "", 1).isdigit() else v
        studio_set(a[1], **kv)
        print("записано", a[1], kv)
    else:
        print(USAGE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
