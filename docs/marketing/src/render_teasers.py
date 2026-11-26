"""Render docs/marketing/src/teasers.html slides to PNG (1080x1350).

Run from anywhere: python docs/marketing/src/render_teasers.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "linkedin" / "teasers"
OUT.mkdir(parents=True, exist_ok=True)
NAMES = {"t1": "teaser-1-building.png", "t2": "teaser-2-appear.png", "t3": "teaser-3-accents.png"}

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
    page.goto((SRC / "teasers.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_timeout(300)
    for sid, name in NAMES.items():
        page.locator(f"#{sid}").screenshot(path=str(OUT / name))
        print("wrote", OUT / name)
    browser.close()
