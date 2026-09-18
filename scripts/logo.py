"""espresso logo: a cup on its saucer seen from a low three-quarter angle, the way a cup
sits in front of you on the table. The rim is a flat ellipse, the bowl of the cup shows
below it, the handle is on the left, and one white quotation pair lies on the surface of
the coffee, foreshortened with it. Ground #8E5643, rounded corners.

    uv run python scripts/logo.py out.png
"""
import fitz, sys

S = 1024
K = 0.42            # vertical squash of the rim: 1.0 is straight down, 0.42 is a low angle
KS = 0.36           # the saucer sits lower, so it is flatter still
bg = (0x8E / 255, 0x56 / 255, 0x43 / 255)
white = (0.97, 0.97, 0.97)
wall = (0.89, 0.87, 0.85)
cream = (0.93, 0.90, 0.86)
shade = (0.84, 0.80, 0.76)
coffee = (0.20, 0.11, 0.07)
crema = (0.55, 0.33, 0.18)

cx, cy = 520, 400   # centre of the rim
R, RB, H = 270, 172, 150   # rim radius, base radius, height of the bowl


def ell(sh, x, y, rx, ry, fill):
    sh.draw_oval(fitz.Rect(x - rx, y - ry, x + rx, y + ry))
    sh.finish(fill=fill, color=None)


doc = fitz.open()
page = doc.new_page(width=S, height=S)
sh = page.new_shape()
sh.draw_rect(page.rect); sh.finish(fill=bg, color=None)

# saucer, behind everything; its far edge shows just under the rim
sy = cy + H + 14
ell(sh, cx, sy, 440, 440 * KS, cream)
ell(sh, cx, sy, 408, 408 * KS, white)
ell(sh, cx, sy + 2, 205, 205 * KS, shade)        # the cup's shadow; only its lower edge shows

# handle on the left, drawn before the bowl so the bowl covers its root
hx, hy = cx - R - 34, cy + 66
ell(sh, hx, hy, 92, 84, white)
ell(sh, hx - 12, hy + 2, 44, 40, bg)             # the hole shows the ground through it

# the bowl: from the rim's widest points down curved sides to a smaller base
P = fitz.Point
sh.draw_line(P(cx - R, cy), P(cx - R, cy))
sh.draw_bezier(P(cx - R, cy), P(cx - R + 2, cy + 80), P(cx - RB - 24, cy + H - 30), P(cx - RB, cy + H))
sh.draw_bezier(P(cx - RB, cy + H), P(cx - RB, cy + H + RB * K * 1.33), P(cx + RB, cy + H + RB * K * 1.33), P(cx + RB, cy + H))
sh.draw_bezier(P(cx + RB, cy + H), P(cx + RB + 24, cy + H - 30), P(cx + R - 2, cy + 80), P(cx + R, cy))
sh.finish(fill=wall, color=None, closePath=True)

# rim, then the coffee a touch lower than the rim's centre so the far inner wall shows
ell(sh, cx, cy, R, R * K, white)
ell(sh, cx, cy + 6, 234, 234 * K, crema)
ell(sh, cx, cy + 8, 214, 214 * K, coffee)
sh.commit()

# the quotation pair on the surface, scaled vertically about the coffee's centre
font = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
fs = 520
qy = cy + 8
tw = fitz.Font(fontfile=font).text_length("“", fontsize=fs)
page.insert_text(P(cx - tw / 2 - 4, qy + 0.524 * fs), "“", fontsize=fs, fontfile=font,
                 fontname="georgiab", color=white, morph=(P(cx, qy), fitz.Matrix(1, 0.52)))

pix = page.get_pixmap(alpha=True)
r = int(S * 0.2)
for y in range(S):
    for x in range(S):
        dx = max(r - x, x - (S - 1 - r), 0); dy = max(r - y, y - (S - 1 - r), 0)
        if dx * dx + dy * dy > r * r:
            pix.set_pixel(x, y, (0, 0, 0, 0))
pix.save(sys.argv[1])
print("wrote", sys.argv[1])
