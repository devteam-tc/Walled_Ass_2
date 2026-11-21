#!/usr/bin/env python3
"""
generate_icons.py — Generates simple placeholder PNG icons for the extension.
Run once: python generate_icons.py
Requires Pillow: pip install Pillow
"""
import os, struct, zlib

def create_png(size, fill=(13, 110, 253)):
    """Create a minimal solid-color PNG without Pillow."""
    def chunk(tag, data):
        c = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", c)

    raw = b""
    for _ in range(size):
        raw += b"\x00" + bytes(fill) * size

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend

out_dir = os.path.join(os.path.dirname(__file__), "extension", "icons")
os.makedirs(out_dir, exist_ok=True)

for size in [16, 48, 128]:
    png_data = create_png(size, fill=(13, 110, 253))  # #0d6efd blue
    path = os.path.join(out_dir, f"icon{size}.png")
    with open(path, "wb") as f:
        f.write(png_data)
    print(f"Created: {path}")

print("Icons generated.")
