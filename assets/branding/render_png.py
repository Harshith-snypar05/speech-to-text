"""Renders the SVG masters to PNG exports with headless Chromium (vector -> raster at each target size)."""
from pathlib import Path

from playwright.sync_api import sync_playwright

B = Path(__file__).parent
E = B / "exports"
E.mkdir(exist_ok=True)
J = {}


def jobs():
    yield "scriptliv-icon.svg", "icon-{}.png", [64, 128, 256, 512, 1024], True
    yield "scriptliv-horizontal-light.svg", "horizontal-light-{}.png", [400, 800, 1600], True
    yield "scriptliv-horizontal-dark.svg", "horizontal-dark-{}.png", [400, 800, 1600], True
    yield "scriptliv-wordmark.svg", "wordmark-{}.png", [400, 800], True
    yield "scriptliv-app-icon.svg", "app-icon-{}.png", [1024, 512, 192], False


with sync_playwright() as p:
    br = p.chromium.launch()
    for svg, name, sizes, _ in jobs():
        src = (B / svg).read_text(encoding="utf-8")
        import re
        vb = [float(x) for x in re.search(r'viewBox="([^"]+)"', src).group(1).split()]
        for s in sizes:
            w = s
            h = round(s * vb[3] / vb[2])
            pg = br.new_page(viewport={"width": w, "height": h})
            pg.set_content(f'<html><body style="margin:0;background:transparent">'
                           f'<img src="data:image/svg+xml;utf8,{__import__("urllib.parse").parse.quote(src)}" width="{w}" height="{h}"></body></html>')
            pg.screenshot(path=str(E / name.format(s)), omit_background=True)
            pg.close()
    br.close()
print(sorted(x.name for x in E.iterdir()))
