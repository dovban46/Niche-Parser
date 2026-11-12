"""python -m app.explainer.make_assets — згенерувати (з кешу) фони й предмети тестового розкадрування."""
from . import assets, samples

if __name__ == "__main__":
    for k, p in samples.BACKGROUNDS.items():
        assets.ensure_bg(k, p)
    for k, p in samples.PROPS.items():
        assets.ensure_prop(k, p)
    print("готово:", assets.ASSET_ROOT)
