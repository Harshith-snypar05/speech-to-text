"""Platform icon sets from the vector masters. Run after build_logo.py + render_png.py."""
import re
import urllib.parse
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

B = Path(__file__).parent
src = (B / "scriptliv-app-icon.svg").read_text(encoding="utf-8")
square = src.replace('rx="230" ', "")                       # full-bleed square for iOS (OS applies the mask)
(B / "scriptliv-app-icon-square.svg").write_text(square, encoding="utf-8")
icon = (B / "scriptliv-icon.svg").read_text(encoding="utf-8")


def render(svg_text, size, path, transparent):
    with sync_playwright() as p:
        br = p.chromium.launch()
        pg = br.new_page(viewport={"width": size, "height": size})
        pg.set_content(f'<body style="margin:0;background:transparent"><img width="{size}" height="{size}" '
                       f'src="data:image/svg+xml;utf8,{urllib.parse.quote(svg_text)}"></body>')
        pg.screenshot(path=str(path), omit_background=transparent)
        br.close()


T = B / "_tmp"
T.mkdir(exist_ok=True)
render(square, 1024, T / "sq.png", False)
render(src, 1024, T / "round.png", True)
# adaptive-icon foreground: emblem in the 66% safe zone of a 108dp canvas, white glyph on transparent
fg_svg = re.sub(r"</?svg[^>]*>", "", icon)
fg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 432 432" width="432" height="432"><g transform="translate(108 108) scale(1.08)">'
      + fg_svg.replace('stroke="url(#g)"', 'stroke="#FFFFFF"').replace('fill="url(#g)"', 'fill="#FFFFFF"') + "</g></svg>")
render(fg, 432, T / "fg.png", True)

sq, rd, fgi = (Image.open(T / n).convert("RGBA") for n in ("sq.png", "round.png", "fg.png"))

# favicon
fav = B / "favicon"
fav.mkdir(exist_ok=True)
ic = Image.open(B / "exports" / "icon-256.png").convert("RGBA")
ic.save(fav / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
for n in (16, 32, 180, 192, 512):
    (rd if n >= 180 else ic).resize((n, n), Image.LANCZOS).save(fav / f"favicon-{n}.png")

# Android launcher (legacy square-ish + round + adaptive foreground)
dens = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
and_dir = B / "android"
for d, n in dens.items():
    od = and_dir / f"mipmap-{d}"
    od.mkdir(parents=True, exist_ok=True)
    rd.resize((n, n), Image.LANCZOS).save(od / "ic_launcher.png")
    fgi.resize((n * 108 // 48, n * 108 // 48), Image.LANCZOS).save(od / "ic_launcher_foreground.png")
rd.resize((512, 512), Image.LANCZOS).save(and_dir / "play-store-512.png")

# iOS AppIcon.appiconset (no alpha channel allowed)
ios = B / "ios" / "AppIcon.appiconset"
ios.mkdir(parents=True, exist_ok=True)
spec = [("20", 1), ("20", 2), ("20", 3), ("29", 1), ("29", 2), ("29", 3), ("40", 1), ("40", 2), ("40", 3), ("60", 2), ("60", 3),
        ("76", 1), ("76", 2), ("83.5", 2), ("1024", 1)]
imgs = []
for pt, sc in spec:
    px = round(float(pt) * sc)
    name = f"Icon-App-{pt}x{pt}@{sc}x.png"
    sq.convert("RGB").resize((px, px), Image.LANCZOS).save(ios / name)
    idiom = "ios-marketing" if pt == "1024" else ("ipad" if pt in ("76", "83.5") else "iphone")
    imgs.append({"size": f"{pt}x{pt}", "idiom": idiom, "filename": name, "scale": f"{sc}x"})
    if pt in ("20", "29", "40") and sc in (1, 2):
        imgs.append({"size": f"{pt}x{pt}", "idiom": "ipad", "filename": name, "scale": f"{sc}x"})
import json
(ios / "Contents.json").write_text(json.dumps({"images": imgs, "info": {"version": 1, "author": "xcode"}}, indent=2))
import shutil
shutil.rmtree(T)
print("ok")
