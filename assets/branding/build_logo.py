"""Builds the ScriptLiv logo master SVGs and PNG exports.

Wordmark: Inter Variable (OFL) instanced at weight 800, converted to outlines with fontTools, so the SVG does not
depend on an installed font. Emblem: two S-ribbons around a play triangle with four waveform bars, drawn as vectors.
Run: python build_logo.py <inter-latin-wght-normal.woff2>
"""
import sys
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

OUT = Path(__file__).parent
NAVY, PURPLE, VIOLET, LAV = "#0F172A", "#6A00FF", "#A855F7", "#E9D5FF"

font = TTFont(sys.argv[1])
font = instancer.instantiateVariableFont(font, {"wght": 800})
gs, cmap, upm = font.getGlyphSet(), font.getBestCmap(), font["head"].unitsPerEm
hmtx = font["hmtx"]


def text_path(text, size, x0, baseline, tracking=-0.02):
    """-> (svg path d, end x)"""
    s, x, parts = size / upm, x0, []
    for ch in text:
        g = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, baseline)))
        parts.append(pen.getCommands())
        x += hmtx[g][0] * s + tracking * size
    return " ".join(parts), x


# ---- emblem, 200x200 box: two S-ribbons (stroked, round caps) around a play triangle, 4 waveform bars on the right
TOP = "M140 36 H86 C56 36 34 52 34 76 C34 92 44 100 58 102"
BOT = "M30 166 H86 C114 166 130 152 130 134 C130 126 126 120 120 118"


def emblem(grad="g", tri=NAVY, ribbon=None, bar=None):
    r = ribbon or f"url(#{grad})"
    br = bar or f"url(#{grad})"
    defs = (f'<defs><linearGradient id="{grad}" gradientUnits="userSpaceOnUse" x1="20" y1="20" x2="190" y2="180">'
            f'<stop offset="0" stop-color="{PURPLE}"/><stop offset="1" stop-color="{VIOLET}"/></linearGradient></defs>')
    return (defs + f'<g fill="none" stroke="{r}" stroke-width="24" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="{TOP}"/><path d="{BOT}"/></g>'
            f'<path fill="{tri}" stroke="{tri}" stroke-width="6" stroke-linejoin="round" d="M80 80 L80 120 L112 100 Z"/>'
            f'<g fill="{br}"><rect x="134" y="88" width="10" height="24" rx="5"/><rect x="150" y="72" width="10" height="56" rx="5"/>'
            f'<rect x="166" y="62" width="10" height="76" rx="5"/><rect x="182" y="80" width="10" height="40" rx="5"/></g>')


def svg(w, h, body, extra=""):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}"{extra}>{body}</svg>\n'


# icon (transparent)
(OUT / "scriptliv-icon.svg").write_text(svg(200, 200, emblem()), encoding="utf-8")

# horizontal lockup: emblem 200 + gap + wordmark
SIZE, BASE = 150, 142
d1, x1 = text_path("Script", SIZE, 218, BASE)
d2, x2 = text_path("Liv", SIZE, x1, BASE)
W = int(x2 + 12)


def lockup(c1, c2, tri, grad):
    return svg(W, 200, emblem(grad, tri) + f'<path fill="{c1}" d="{d1}"/><path fill="{c2}" d="{d2}"/>')


(OUT / "scriptliv-horizontal-light.svg").write_text(lockup(NAVY, PURPLE, NAVY, "gl"), encoding="utf-8")        # for light backgrounds
(OUT / "scriptliv-horizontal-dark.svg").write_text(lockup("#F9FAFB", "#A78BFA", "#F9FAFB", "gd"), encoding="utf-8")  # for dark backgrounds
d3, x3 = text_path("Script", 150, 0, 142)
d4, x4 = text_path("Liv", 150, x3, 142)
(OUT / "scriptliv-wordmark.svg").write_text(
    svg(int(x4) + 12, 200, f'<path fill="{NAVY}" d="{d3}"/><path fill="{PURPLE}" d="{d4}"/>'), encoding="utf-8")

# app icon master: rounded square, brand gradient, white emblem
app_body = (f'<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{PURPLE}"/>'
            f'<stop offset="1" stop-color="{VIOLET}"/></linearGradient></defs>'
            f'<rect width="1024" height="1024" rx="230" fill="url(#bg)"/>'
            f'<g transform="translate(182 182) scale(3.3)">' + emblem("w", "#0B1220", "#FFFFFF", "#FFFFFF") + '</g>')
(OUT / "scriptliv-app-icon.svg").write_text(svg(1024, 1024, app_body), encoding="utf-8")
print("svg ok", W)
