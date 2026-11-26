"""Render Instagram-specific assets from the same HTML sources.

Output (docs/marketing/instagram/):
  feed/      1080x1350 (4:5): teasers, carousel slides (last slide says "link in bio"),
             fixed-before-after, waitlist-reminder
  stories/   1080x1920 (9:16): teasers, fixed-before-after, waitlist (leave room for link sticker)
  reels/     1080x1920 (9:16) MP4: logo reveal, live demo

Stories/Reels keep the 4:5 art centred inside the 9:16 frame, clear of Instagram's
top/bottom UI zones, on a continuous brand gradient.

Needs: pip install playwright imageio-ffmpeg
Run:   python docs/marketing/src/render_instagram.py
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
LI = SRC.parent / "linkedin"
OUT = SRC.parent / "instagram"
for d in ("feed", "stories", "reels"):
    (OUT / d).mkdir(parents=True, exist_ok=True)
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30

TELL = {"t1": "teaser-1-building", "t2": "teaser-2-appear", "t3": "teaser-3-accents"}


def wait_ready(page):
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every(i => i.complete)")
    page.wait_for_timeout(400)


def tall_frame(page, target_sel, others_sel, top):
    """Place target in a 1080x1920 gradient page at `top`, hide the rest."""
    page.add_style_tag(content=f"""
      html,body{{margin:0;width:1080px;height:1920px;overflow:hidden;position:relative;
        background:linear-gradient(180deg,#1B0B33 0%,#2B0F52 100%) !important}}
      {others_sel}{{display:none !important}}
      {target_sel}{{display:block !important;position:absolute !important;left:0;top:{top}px;
        background:transparent !important;overflow:visible !important}}
    """)


def story_png(page, html, sid, top, path, edit=None):
    page.goto((SRC / html).as_uri())
    wait_ready(page)
    if edit:
        page.evaluate(edit)
    sel = f"#{sid}"
    ids = [s for s in ("t1", "t2", "t3", "ba", "wl") if s != sid]
    tall_frame(page, sel, ", ".join(f"#{i}" for i in ids), top)
    page.wait_for_timeout(200)
    page.screenshot(path=str(path))
    print("wrote", path)


def reel(page, html, path, duration, top):
    page.goto((SRC / html).as_uri())
    wait_ready(page)
    tall_frame(page, "#stage", ".none", top)
    enc = subprocess.Popen(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(path)],
        stdin=subprocess.PIPE)
    for i in range(int(FPS * duration)):
        page.evaluate(f"frame({i / FPS})")
        enc.stdin.write(page.screenshot(type="png"))
    enc.stdin.close()
    enc.wait()
    print("wrote", path)


WL_FEED = ("document.querySelector('#wl .btn').textContent='Waitlist: link in bio';"
           "document.querySelector('#wl .note').textContent='Web app: scriptliv.com';")
WL_STORY = ("document.querySelector('#wl .btn').innerHTML='Join the waitlist &#8595;';"
            "document.querySelector('#wl .note').textContent='Tap the link sticker below';")

with sync_playwright() as p:
    browser = p.chromium.launch()
    wide = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)

    # ---- feed (4:5) ----
    wide.goto((SRC / "teasers.html").as_uri())
    wait_ready(wide)
    for sid, name in TELL.items():
        wide.locator(f"#{sid}").screenshot(path=str(OUT / "feed" / f"{name}.png"))

    wide.goto((SRC / "carousel.html").as_uri())
    wait_ready(wide)
    wide.evaluate(
        "const s=[...document.querySelectorAll('.slide')].pop().querySelector('p.sub');"
        "s.innerHTML='Android app coming soon.<br>Join the waitlist: link in bio.';")
    slides = wide.locator(".slide")
    for i in range(slides.count()):
        slides.nth(i).screenshot(path=str(OUT / "feed" / f"carousel-{i:02d}.png"))

    wide.goto((SRC / "static.html").as_uri())
    wait_ready(wide)
    wide.locator("#ba").screenshot(path=str(OUT / "feed" / "fixed-before-after.png"))
    wide.evaluate(WL_FEED)
    wide.locator("#wl").screenshot(path=str(OUT / "feed" / "waitlist-reminder.png"))
    print("feed done")

    # ---- stories (9:16), art centred: top/bottom 285 px stay clear ----
    tall = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    for sid, name in TELL.items():
        story_png(tall, "teasers.html", sid, 285, OUT / "stories" / f"{name}.png")
    story_png(tall, "static.html", "ba", 285, OUT / "stories" / "fixed-before-after.png")
    story_png(tall, "static.html", "wl", 285, OUT / "stories" / "waitlist.png", edit=WL_STORY)

    # ---- reels (9:16 MP4) ----
    reel_page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    reel(reel_page, "reveal.html", OUT / "reels" / "logo-reveal-1080x1920.mp4", 8.0, 230)
    reel_page = browser.new_page(viewport={"width": 1080, "height": 1920}, device_scale_factor=1)
    reel(reel_page, "demo.html", OUT / "reels" / "live-demo-1080x1920.mp4", 10.0, 230)
    browser.close()
print("done")
