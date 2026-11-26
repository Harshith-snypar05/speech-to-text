"""Render carousel.html to 8 PNG slides (1080x1350) and one PDF (LinkedIn document post).

Run: python docs/marketing/src/render_carousel.py
Output: docs/marketing/linkedin/carousel/slide-0N.png and docs/marketing/linkedin/scriptliv-intro-carousel.pdf
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "linkedin" / "carousel"
OUT.mkdir(parents=True, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
    page.goto((SRC / "carousel.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every(i => i.complete)")
    page.wait_for_timeout(500)
    slides = page.locator(".slide")
    for i in range(slides.count()):
        path = OUT / f"slide-{i:02d}.png"
        slides.nth(i).screenshot(path=str(path))
        print("wrote", path)
    pdf = SRC.parent / "linkedin" / "scriptliv-intro-carousel.pdf"
    page.pdf(path=str(pdf), width="1080px", height="1350px", print_background=True, prefer_css_page_size=True)
    print("wrote", pdf)
    browser.close()
