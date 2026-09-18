"""The repository's social preview (docs/assets/social-preview.png, 1280x640): the README's
header, the cup above "espresso", on the app's black, with the tagline under it. GitHub shows
it when the repository link is shared. Upload it under Settings, General, Social preview.

    uv run --project backend python scripts/social-preview.py GEIST_REGULAR.ttf
"""
import sys

import fitz

W, H = 1280, 640
GROUND = (0x0B / 255, 0x0B / 255, 0x0B / 255)
GREY = (0x9A / 255, 0x9A / 255, 0x9A / 255)
LOCKUP = "docs/assets/wordmark-dark.png"
TAGLINE = "Catch up on papers, and stay awake."
OUT = "docs/assets/social-preview.png"

font_path = sys.argv[1]
doc = fitz.open()
page = doc.new_page(width=W, height=H)
page.draw_rect(page.rect, color=None, fill=GROUND)
lockup = fitz.Pixmap(LOCKUP)
h = 330
w = lockup.width * h / lockup.height
top = 108
page.insert_image(fitz.Rect((W - w) / 2, top, (W + w) / 2, top + h), pixmap=lockup)
size = 30
tw = fitz.Font(fontfile=font_path).text_length(TAGLINE, fontsize=size)
page.insert_text(fitz.Point((W - tw) / 2, top + h + 62), TAGLINE, fontsize=size, fontfile=font_path,
                 fontname="geist", color=GREY)
page.get_pixmap(alpha=False).save(OUT)
print("wrote", OUT)
