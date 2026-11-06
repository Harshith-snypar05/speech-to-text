"""Draws attention marks (rounded boxes / circles / arrows) on raw app
screenshots for the user manual. Pure visual markers -- explanations live
in the manual's prose, not baked into the image.
"""
from PIL import Image, ImageDraw

MARK = (255, 176, 32)  # warm amber -- high contrast against the dark UI
WIDTH = 5


def rrect(draw, box, color=MARK, width=WIDTH, radius=14):
    draw.rounded_rectangle(box, radius=radius, outline=color, width=width)


def circle(draw, center, radius, color=MARK, width=WIDTH):
    x, y = center
    draw.ellipse([x - radius, y - radius, x + radius, y + radius], outline=color, width=width)


def arrow_up(draw, x, y_tail, y_head, color=MARK, width=WIDTH):
    draw.line([x, y_tail, x, y_head], fill=color, width=width)
    head = 16
    draw.line([x - head, y_head + head, x, y_head], fill=color, width=width)
    draw.line([x + head, y_head + head, x, y_head], fill=color, width=width)


def run(src, dst, shapes):
    img = Image.open(src).convert("RGB")
    draw = ImageDraw.Draw(img)
    for shape in shapes:
        kind = shape["type"]
        if kind == "rect":
            rrect(draw, shape["box"])
        elif kind == "circle":
            circle(draw, shape["center"], shape["radius"])
        elif kind == "arrow_up":
            arrow_up(draw, shape["x"], shape["y_tail"], shape["y_head"])
    img.save(dst)
    print(dst)


if __name__ == "__main__":
    A = "manual_assets"

    run(f"{A}/raw_01b_login_filled.png", f"{A}/final_01_login.png", [
        {"type": "rect", "box": [450, 350, 830, 520]},
    ])

    run(f"{A}/raw_02_home.png", f"{A}/final_02_home.png", [
        {"type": "rect", "box": [10, 80, 1270, 148]},
    ])

    run(f"{A}/raw_03_session_idle.png", f"{A}/final_03_mic.png", [
        {"type": "circle", "center": [640, 212], "radius": 110},
    ])

    run(f"{A}/raw_05_access_code_on.png", f"{A}/final_04_access_code.png", [
        {"type": "rect", "box": [545, 353, 730, 389]},
    ])

    run(f"{A}/raw_06_recording.png", f"{A}/final_05_recording.png", [
        {"type": "circle", "center": [640, 212], "radius": 110},
        {"type": "arrow_up", "x": 1150, "y_tail": 650, "y_head": 600},
    ])

    run(f"{A}/raw_06_recording.png", f"{A}/final_06_drag_handle.png", [
        {"type": "arrow_up", "x": 640, "y_tail": 672, "y_head": 630},
        {"type": "rect", "box": [560, 680, 720, 696]},
    ])

    run(f"{A}/raw_04_settings.png", f"{A}/final_07_settings.png", [
        {"type": "rect", "box": [10, 58, 1270, 96]},
        {"type": "rect", "box": [10, 133, 1270, 171]},
        {"type": "rect", "box": [10, 181, 1270, 219]},
        {"type": "rect", "box": [10, 262, 1270, 300]},
    ])

    run(f"{A}/raw_08_share_sheet.png", f"{A}/final_08_share_link.png", [
        {"type": "rect", "box": [335, 592, 945, 627]},
        {"type": "rect", "box": [335, 646, 945, 682]},
    ])

    run(f"{A}/raw_09_before_end.png", f"{A}/final_09_end_session.png", [
        {"type": "rect", "box": [570, 350, 710, 382]},
    ])

    run(f"{A}/raw_10_home_after.png", f"{A}/final_10_saved.png", [
        {"type": "rect", "box": [10, 208, 1270, 280]},
    ])

    run(f"{A}/raw_11_viewer_ended.png", f"{A}/final_11_ended_link.png", [
        {"type": "rect", "box": [10, 8, 300, 36]},
    ])
