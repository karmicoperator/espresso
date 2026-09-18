"""espresso logo, a three-quarter view from above: the rim and saucer are ellipses, a short
cup wall shows below the rim, a handle on the right, and one white quotation pair sits on
the surface of the coffee, foreshortened with it. Ground #8E5643, rounded corners."""
import fitz, sys
S = 1024
K = 0.66            # vertical squash of every circle: 1.0 is straight down, ~0.7 is a 3/4 view
doc = fitz.open(); page = doc.new_page(width=S, height=S)
bg = (0x8E/255, 0x56/255, 0x43/255)
white = (0.97, 0.97, 0.97)
wall = (0.88, 0.86, 0.84)
cream = (0.93, 0.90, 0.86)
lip = (0.86, 0.82, 0.78)
coffee = (0.20, 0.11, 0.07)
crema = (0.55, 0.33, 0.18)
cx, cy = 496, 452   # centre of the rim
def ell(sh, x, y, rx, ry, fill):
    sh.draw_oval(fitz.Rect(x - rx, y - ry, x + rx, y + ry)); sh.finish(fill=fill, color=None)
sh = page.new_shape()
sh.draw_rect(page.rect); sh.finish(fill=bg, color=None)
# saucer, sitting lower than the rim
sy = cy + 135
ell(sh, cx, sy, 420, 420 * K, cream)
ell(sh, cx, sy, 390, 390 * K, white)
ell(sh, cx, cy + 96 + 14, 250, 250 * K, lip)     # the cup's shadow on the saucer: only its lower edge shows past the base
# handle, drawn first so the cup wall covers its root
hx, hy = cx + 268 + 48, cy + 56
ell(sh, hx, hy, 98, 98 * 0.9, white)
ell(sh, hx + 12, hy, 50, 50 * 0.9, lip)
# cup wall: from the rim's sides down to a smaller bottom ellipse
R, H, RB = 268, 96, 240
p = sh
p.draw_line(fitz.Point(cx - R, cy), fitz.Point(cx - RB, cy + H))
p.draw_bezier(fitz.Point(cx - RB, cy + H), fitz.Point(cx - RB, cy + H + RB * K * 1.33),
              fitz.Point(cx + RB, cy + H + RB * K * 1.33), fitz.Point(cx + RB, cy + H))
p.draw_line(fitz.Point(cx + RB, cy + H), fitz.Point(cx + R, cy))
p.finish(fill=wall, color=None, closePath=True)
# rim, crema, coffee
ell(sh, cx, cy, R, R * K, white)
ell(sh, cx, cy, 228, 228 * K, crema)
ell(sh, cx, cy, 206, 206 * K, coffee)
sh.commit()
# the quotation pair on the surface: scaled vertically about the cup centre so it lies in the plane
font = "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"
fs = 500
tw = fitz.Font(fontfile=font).text_length("“", fontsize=fs)
page.insert_text(fitz.Point(cx - tw / 2 - 4, cy + 0.524 * fs), "“", fontsize=fs, fontfile=font,
                 fontname="georgiab", color=white, morph=(fitz.Point(cx, cy), fitz.Matrix(1, 0.8)))
pix = page.get_pixmap(alpha=True)
r = int(S * 0.2)
for y in range(S):
    for x in range(S):
        dx = max(r - x, x - (S - 1 - r), 0); dy = max(r - y, y - (S - 1 - r), 0)
        if dx * dx + dy * dy > r * r:
            pix.set_pixel(x, y, (0, 0, 0, 0))
pix.save(sys.argv[1]); print("ok")
