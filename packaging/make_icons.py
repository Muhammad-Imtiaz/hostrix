"""Render the SVG logo into the icon files the installers need.

    python packaging/make_icons.py   ->  packaging/icons/hostrix.{png,ico,icns}

Needs PySide6 (already a dependency) and Pillow. The outputs are committed, so this only
has to be re-run when the logo changes.
"""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parent.parent
SVG = ROOT / "hostrix" / "assets" / "hostrix.svg"
OUT = ROOT / "packaging" / "icons"


def render(size: int) -> QImage:
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    QSvgRenderer(str(SVG)).render(p, QRectF(0, 0, size, size))
    p.end()
    return img


def main():
    app = QGuiApplication([])  # QSvgRenderer needs a GUI application
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / "hostrix.png"
    render(1024).save(str(png))
    base = Image.open(png)
    base.save(OUT / "hostrix.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    base.save(OUT / "hostrix.icns")
    app.quit()
    print("wrote", ", ".join(p.name for p in sorted(OUT.iterdir())))


if __name__ == "__main__":
    main()
