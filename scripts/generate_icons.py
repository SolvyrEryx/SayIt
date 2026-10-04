"""Generate SayIt's platform icon assets from the canonical SVG."""
from __future__ import annotations
import argparse
import os
import struct
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "icons" / "sayit.svg"
OUTPUT = ROOT / "icons"
SIZES = (16, 32, 48, 64, 128, 256, 512)
ICO_SIZES = (16, 32, 48, 64, 128, 256)

def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # QSvgRenderer.render() is a void C++ method; PySide6 therefore returns
    # None rather than a success boolean. Treating that return value as a
    # boolean made every otherwise-valid render look like a failure.
    renderer.render(painter)
    painter.end()
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise RuntimeError("Unable to open in-memory PNG buffer")
    if not image.save(buffer, "PNG"):
        raise RuntimeError(f"Failed to encode {size}px PNG")
    return bytes(buffer.data())

def build_ico(pngs: dict[int, bytes]) -> bytes:
    header = struct.pack("<HHH", 0, 1, len(ICO_SIZES))
    entries = bytearray()
    payload = bytearray()
    offset = 6 + (16 * len(ICO_SIZES))
    for size in ICO_SIZES:
        data = pngs[size]
        dim = 0 if size == 256 else size
        entries.extend(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        payload.extend(data)
        offset += len(data)
    return header + bytes(entries) + bytes(payload)

def check() -> None:
    expected = [OUTPUT / f"sayit-{size}.png" for size in SIZES]
    expected += [OUTPUT / "sayit.png", OUTPUT / "sayit.ico"]
    missing = [str(path) for path in expected if not path.is_file()]
    if missing:
        raise RuntimeError("Missing generated icon assets:\n" + "\n".join(missing))
    signature = b"\x89PNG\r\n\x1a\n"
    for size in SIZES:
        data = (OUTPUT / f"sayit-{size}.png").read_bytes()
        if not data.startswith(signature):
            raise RuntimeError(f"Invalid PNG: sayit-{size}.png")
    ico = (OUTPUT / "sayit.ico").read_bytes()
    if len(ico) < 6 or ico[:4] != b"\x00\x00\x01\x00":
        raise RuntimeError("Invalid ICO header")
    count = struct.unpack_from("<H", ico, 4)[0]
    if count != len(ICO_SIZES):
        raise RuntimeError(f"Expected {len(ICO_SIZES)} ICO images, found {count}")
    dims = set()
    for i in range(count):
        off = 6 + (16 * i)
        width, height = ico[off], ico[off + 1]
        width = 256 if width == 0 else width
        height = 256 if height == 0 else height
        if width != height:
            raise RuntimeError("ICO entry is not square")
        dims.add(width)
    if dims != set(ICO_SIZES):
        raise RuntimeError(f"ICO sizes {sorted(dims)} != {list(ICO_SIZES)}")

def generate() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(f"Canonical icon source missing: {SOURCE}")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance()
    owned = app is None
    if owned:
        app = QGuiApplication([])
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {SOURCE}")
    pngs = {}
    for size in SIZES:
        pngs[size] = render_png(renderer, size)
        (OUTPUT / f"sayit-{size}.png").write_bytes(pngs[size])
    (OUTPUT / "sayit.png").write_bytes(pngs[256])
    (OUTPUT / "sayit.ico").write_bytes(build_ico(pngs))
    check()
    if owned:
        app.quit()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        generate()
        print("SayIt icon assets generated and validated.")

if __name__ == "__main__":
    main()
