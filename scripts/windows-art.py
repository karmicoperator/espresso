"""Windows artwork from the logo: the app and installer icon (windows/espresso.ico) and the
side panel of the installer's first and last pages (windows/installer-side.bmp, 164x314,
the size NSIS's Modern UI expects).

    uvx --with pillow python scripts/windows-art.py
"""
from PIL import Image

LOGO = "frontend/public/icon.png"
WORDMARK = "docs/assets/wordmark-dark.png"   # light text, for the brown panel
GROUND = (0x8E, 0x56, 0x43)

logo = Image.open(LOGO).convert("RGBA")
logo.save("windows/espresso.ico", sizes=[(s, s) for s in (16, 20, 24, 32, 40, 48, 64, 128, 256)])

panel = Image.new("RGB", (164, 314), GROUND)
mark = Image.open(WORDMARK).convert("RGBA")
w = 124
mark = mark.resize((w, round(mark.height * w / mark.width)), Image.LANCZOS)
panel.paste(mark, ((164 - w) // 2, 70), mark)
panel.save("windows/installer-side.bmp")
print("wrote windows/espresso.ico and windows/installer-side.bmp")
