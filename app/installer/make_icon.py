"""Make the app icons from the LIBRA logo (randomizer_gui/assets/logo.png, 512 × 512 with transparency).

    python installer/make_icon.py

Writes installer/icon.ico (Windows: exe, installer, .libra files), installer/icon.png (macOS app; PyInstaller
turns it into .icns) and randomizer_gui/assets/icon.png + icon.ico (window and taskbar icon).
"""
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ASSETS = HERE.parent / "randomizer_gui" / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def main():
    logo = Image.open(ASSETS / "logo.png").convert("RGBA")
    # each size is resampled from the original on its own, so small icons stay crisp
    frames = [logo.resize((s, s), Image.Resampling.LANCZOS) for s in SIZES]
    for ico in (HERE / "icon.ico", ASSETS / "icon.ico"):
        frames[-1].save(ico, format="ICO", sizes=[(s, s) for s in SIZES], append_images=frames[:-1])
    for png in (HERE / "icon.png", ASSETS / "icon.png"):
        shutil.copyfile(ASSETS / "logo.png", png)
    print("wrote", HERE / "icon.ico", "and", HERE / "icon.png")


if __name__ == "__main__":
    main()
