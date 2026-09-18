"""The disk-image window's background: brand ground, an arrow from the app to Applications,
and one or two lines saying what to do. Written at 1x and 2x for Retina.

    uv run --project backend python scripts/mac/dmg-background.py OUT_DIR [--unsigned]

The window is 660x400 points; the icons sit at (170, 170) and (490, 170), 128 points wide.
With --unsigned the bottom lines explain the one-time approval macOS asks for.
"""
import math
import sys

import fitz

W, H = 660, 400
GROUND = (0x8E / 255, 0x56 / 255, 0x43 / 255)
CREAM = (0.97, 0.94, 0.90)
SOFT = (0.93, 0.86, 0.80)
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def centred(page, y, text, size, colour, fontfile, name):
    width = fitz.Font(fontfile=fontfile).text_length(text, fontsize=size)
    page.insert_text(fitz.Point((W - width) / 2, y), text, fontsize=size, fontfile=fontfile,
                     fontname=name, color=colour)


def draw(out, scale, unsigned):
    doc = fitz.open()
    page = doc.new_page(width=W, height=H)
    sh = page.new_shape()
    sh.draw_rect(page.rect); sh.finish(fill=GROUND, color=None)
    # arrow between the icons, a gentle arc so it reads as a gesture
    a, c1, c2, b = fitz.Point(262, 176), fitz.Point(300, 150), fitz.Point(356, 150), fitz.Point(394, 176)
    sh.draw_bezier(a, c1, c2, b)
    sh.finish(color=CREAM, width=5, lineCap=1, closePath=False)
    # the head follows the curve: its two strokes sit at +-35 degrees off the end tangent
    tx, ty = b.x - c2.x, b.y - c2.y
    n = math.hypot(tx, ty); tx, ty = tx / n, ty / n
    head = []
    for ang in (35, -35):
        r = math.radians(ang)
        dx, dy = tx * math.cos(r) - ty * math.sin(r), tx * math.sin(r) + ty * math.cos(r)
        head.append(fitz.Point(b.x - 20 * dx, b.y - 20 * dy))
    sh.draw_polyline([head[0], b, head[1]])
    sh.finish(color=CREAM, width=5, lineCap=1, lineJoin=1, closePath=False)
    sh.commit()
    centred(page, 300, "Drag espresso onto Applications", 17, CREAM, FONT_BOLD, "arialb")
    if unsigned:
        centred(page, 330, "The first time you open it, macOS asks you to confirm an app from", 12, SOFT, FONT, "arial")
        centred(page, 348, "outside the App Store: System Settings, Privacy & Security, Open Anyway.", 12, SOFT, FONT, "arial")
    page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).save(out)


if __name__ == "__main__":
    out_dir, unsigned = sys.argv[1], "--unsigned" in sys.argv
    draw(f"{out_dir}/background.png", 1, unsigned)
    draw(f"{out_dir}/background@2x.png", 2, unsigned)
    print("background written", "(unsigned note)" if unsigned else "")
