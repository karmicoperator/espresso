"""The README's header: the logo above "espresso", as on the landing page. Two versions,
light text for GitHub's dark theme and dark text for its light theme, on a transparent
ground.

    uv run --project backend python scripts/wordmark.py GEIST_SEMIBOLD.ttf

The title is Geist (SIL Open Font License) at weight 600 with -0.025em tracking, the
landing page's `text-7xl font-semibold tracking-tight`. Geist ships as a variable web font;
a static SemiBold comes from `fonttools varLib.instancer Geist.ttf wght=600`.
"""
import sys

import fitz

ICON = "frontend/public/icon.png"
OUT = "docs/assets/wordmark-{}.png"
LOGO = 104
SIZE = 76
TRACK = -0.025 * SIZE
X_HEIGHT = 0.534  # Geist's OS/2 sxHeight, 534 of 1000 units
SCALE = 3
TEXT = {"dark": (0xE8 / 255, 0xE8 / 255, 0xE8 / 255), "light": (0x1F / 255, 0x23 / 255, 0x28 / 255)}


def lockup(font_path, theme):
    font = fitz.Font(fontfile=font_path)
    word = "espresso"
    widths = [font.text_length(c, fontsize=SIZE) for c in word]
    total = sum(widths) + TRACK * (len(word) - 1)
    # The landing page leaves about 0.4 of the logo's height between the cup and the top of
    # the lowercase letters; "espresso" has no ascenders, so the x-height is the top.
    baseline = LOGO + 0.4 * LOGO + X_HEIGHT * SIZE
    height = baseline - font.descender * SIZE + 4
    W = max(total, LOGO) + 24
    doc = fitz.open()
    page = doc.new_page(width=W, height=height)
    page.insert_image(fitz.Rect((W - LOGO) / 2, 0, (W + LOGO) / 2, LOGO), filename=ICON)
    x = (W - total) / 2
    for c, w in zip(word, widths):
        page.insert_text(fitz.Point(x, baseline), c, fontsize=SIZE, fontfile=font_path,
                         fontname="geistsb", color=TEXT[theme])
        x += w + TRACK
    page.get_pixmap(matrix=fitz.Matrix(SCALE, SCALE), alpha=True).save(OUT.format(theme))
    return OUT.format(theme)


if __name__ == "__main__":
    for theme in ("dark", "light"):
        print("wrote", lockup(sys.argv[1], theme))
