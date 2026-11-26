"""Render demo.html -> MP4 + GIF, static.html -> fixed-before-after.png + waitlist-reminder.png.

Needs: pip install playwright imageio-ffmpeg
Run: python docs/marketing/src/render_assets.py
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "linkedin"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS, DURATION = 30, 10.0
MP4 = OUT / "live-demo-1080x1350.mp4"
GIF = OUT / "live-demo.gif"

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)

    page.goto((SRC / "static.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_function("[...document.images].every(i => i.complete)")
    page.wait_for_timeout(400)
    page.locator("#ba").screenshot(path=str(OUT / "fixed-before-after.png"))
    page.locator("#wl").screenshot(path=str(OUT / "waitlist-reminder.png"))

    page.goto((SRC / "demo.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_function("document.getElementById('logo').complete")
    enc = subprocess.Popen(
        [FFMPEG, "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
         "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
         "-movflags", "+faststart", str(MP4)],
        stdin=subprocess.PIPE)
    stage = page.locator("#stage")
    for i in range(int(FPS * DURATION)):
        page.evaluate(f"frame({i / FPS})")
        enc.stdin.write(stage.screenshot(type="png"))
    enc.stdin.close()
    enc.wait()
    browser.close()

subprocess.run(
    [FFMPEG, "-y", "-loglevel", "error", "-i", str(MP4),
     "-vf", "fps=15,scale=540:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4",
     str(GIF)], check=True)
print("done")
