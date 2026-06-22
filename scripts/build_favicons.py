"""Slice rook_kit.png into the app's favicons / touch icons.

rook_kit.png (repo root, NOT committed) is a single image with 5 transparent-
background icon tiles. This crops each tile by FRACTIONAL boxes (resolution-
independent), square-pads with transparency before resizing (no distortion), and
writes correctly-sized PNGs to frontend/public/.

Detail-matched: the 32 and 16 come from the SIMPLIFIED bottom-row tiles, not from
shrinking the hero.

Run (Pillow is not a project dep — inject it ephemerally):
    uv run --with pillow python scripts/build_favicons.py

First run writes raw crops to frontend/public/_debug_crops/ for visual review.
Delete that folder once the crops are verified; it is not committed.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "rook_kit.png"
OUT = ROOT / "frontend" / "public"
DEBUG = OUT / "_debug_crops"

# GENEROUS rough boxes (left, top, right, bottom) as fractions — each must
# enclose its tile (with margin) WITHOUT reaching a neighboring tile or that
# tile's caption. The exact helmet/card bounds are then found by auto_trim(),
# so these don't have to be pixel-perfect — just bound the right tile.
ROUGH: dict[str, tuple[float, float, float, float]] = {
    "hero":  (0.010, 0.030, 0.480, 0.710),
    "med":   (0.490, 0.050, 0.700, 0.520),
    "apple": (0.718, 0.050, 0.965, 0.520),
    "fav32": (0.490, 0.560, 0.670, 0.870),
    "fav16": (0.725, 0.585, 0.895, 0.865),
}

# Auto-trim mode per tile: the hero sits on TRANSPARENCY (trim by alpha); the
# others sit on a WHITE CARD over a dark background (trim to the bright card,
# then inset to drop the rounded-corner edge + border).
TRIM = {
    "hero":  ("alpha", 0.0),
    "med":   ("bright", 0.05),
    "apple": ("bright", 0.05),
    "fav32": ("bright", 0.06),
    "fav16": ("bright", 0.06),
}


def crop(im: Image.Image, box: tuple[float, float, float, float]) -> Image.Image:
    w, h = im.size
    l, t, r, b = box
    return im.crop((round(l * w), round(t * h), round(r * w), round(b * h)))


def _content_bbox(c: Image.Image, mode: str):
    """Bounding box of the tile's real content within a rough crop.

    alpha  → opaque pixels (hero, on transparency).
    bright → the white card (luminance high), which excludes the dark card
             background AND the grey caption text below it.
    """
    px = c.convert("RGBA").load()
    w, h = c.size
    minx, miny, maxx, maxy = w, h, -1, -1
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if mode == "alpha":
                hit = a > 30
            else:  # bright: the white card (caption grey ~<160 is excluded)
                hit = a > 30 and (r + g + b) / 3 > 180
            if hit:
                minx, miny = min(minx, x), min(miny, y)
                maxx, maxy = max(maxx, x), max(maxy, y)
    if maxx < 0:
        return (0, 0, w, h)
    return (minx, miny, maxx + 1, maxy + 1)


def auto_trim(c: Image.Image, mode: str, inset: float) -> Image.Image:
    """Trim a rough crop to its content bbox, then inset by `inset` fraction of
    the bbox to drop the rounded-card edge / outline halo."""
    l, t, r, b = _content_bbox(c, mode)
    bw, bh = r - l, b - t
    dx, dy = round(bw * inset), round(bh * inset)
    return c.crop((l + dx, t + dy, r - dx, b - dy))


def square_pad(im: Image.Image) -> Image.Image:
    """Center the crop on a transparent square canvas (no distortion on resize)."""
    im = im.convert("RGBA")
    side = max(im.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(im, ((side - im.width) // 2, (side - im.height) // 2), im)
    return canvas


def resized(im: Image.Image, size: int) -> Image.Image:
    return square_pad(im).resize((size, size), Image.LANCZOS)


def dominant_navy(hero: Image.Image) -> str:
    """Most common navy-blue helmet color in the hero tile (opaque, blue-dominant,
    mid/dark) — the brand color, quantized to a stable hex."""
    px = hero.convert("RGBA").getdata()
    buckets: Counter = Counter()
    for r, g, b, a in px:
        if a < 200:
            continue
        # navy: blue is the dominant channel, not near-white, not near-black
        if b > r and b > g and 25 < b < 230 and (b - max(r, g)) > 20:
            buckets[(r & ~7, g & ~7, b & ~7)] += 1  # quantize to 8-steps
    if not buckets:
        return "#1d4ed8"
    r, g, b = buckets.most_common(1)[0][0]
    return f"#{r:02x}{g:02x}{b:02x}"


def main() -> None:
    im = Image.open(SRC).convert("RGBA")
    print(f"source: {SRC.name}  {im.size}")
    OUT.mkdir(parents=True, exist_ok=True)
    DEBUG.mkdir(parents=True, exist_ok=True)

    crops = {}
    for name, box in ROUGH.items():
        mode, inset = TRIM[name]
        crops[name] = auto_trim(crop(im, box), mode, inset)

    # 1) Raw crops for visual verification (review before trusting the outputs).
    for name, c in crops.items():
        c.save(DEBUG / f"{name}.png")
        print(f"  debug crop {name:6} {c.size} -> {DEBUG / (name + '.png')}")

    # 2) Final, detail-matched outputs.
    resized(crops["hero"], 512).save(OUT / "android-chrome-512x512.png")
    resized(crops["med"], 192).save(OUT / "android-chrome-192x192.png")
    resized(crops["apple"], 180).save(OUT / "apple-touch-icon.png")
    resized(crops["fav32"], 32).save(OUT / "favicon-32x32.png")
    resized(crops["fav16"], 16).save(OUT / "favicon-16x16.png")

    # Multi-res .ico from the SIMPLIFIED small tile (more detail at small sizes
    # than shrinking the hero). Pillow generates the 16/32/48 entries.
    square_pad(crops["fav32"]).resize((48, 48), Image.LANCZOS).save(
        OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)]
    )

    print("\nwrote:")
    for f in (
        "android-chrome-512x512.png", "android-chrome-192x192.png",
        "apple-touch-icon.png", "favicon-32x32.png", "favicon-16x16.png",
        "favicon.ico",
    ):
        print(f"  frontend/public/{f}")

    print(f"\nDOMINANT NAVY (brand color): {dominant_navy(crops['hero'])}")
    print(f"\nReview {DEBUG} then delete it (not committed).")


if __name__ == "__main__":
    main()
