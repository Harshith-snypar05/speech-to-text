"""Render reveal.html (frame(t) is deterministic) to an MP4 for LinkedIn / Reels.

Needs: pip install playwright imageio-ffmpeg
Run: python docs/marketing/src/render_reveal.py
Output: docs/marketing/linkedin/logo-reveal-1080x1350.mp4 (8 s, 30 fps, H.264, silent)
"""
import subprocess
from pathlib import Path

import imageio_ffmpeg
from playwright.sync_api import sync_playwright

SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "linkedin" / "logo-reveal-1080x1350.mp4"
FPS, DURATION = 30, 8.0
frames = int(FPS * DURATION)

ffmpeg = subprocess.Popen(
    [
        imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
        "-f", "image2pipe", "-framerate", str(FPS), "-i", "-",
        "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart", str(OUT),
    ],
    stdin=subprocess.PIPE,
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1080, "height": 1350}, device_scale_factor=1)
    page.goto((SRC / "reveal.html").as_uri())
    page.evaluate("document.fonts.ready")
    page.wait_for_function("document.getElementById('logoimg').complete")
    stage = page.locator("#stage")
    for i in range(frames):
        page.evaluate(f"frame({i / FPS})")
        ffmpeg.stdin.write(stage.screenshot(type="png"))
    browser.close()

ffmpeg.stdin.close()
ffmpeg.wait()
print("wrote", OUT, "frames", frames)
