"""Generate LearnLoop's icon and social-preview assets from the SVG mark.

    python tools/make_brand_assets.py

Writes into static/: icon-192.png, icon-512.png, apple-touch-icon.png,
favicon.ico and og.png (1200x630). Everything is drawn at 4x and downsampled,
then saved with PNG optimisation so the files stay small.
"""
from __future__ import annotations

import io
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

STATIC = Path(__file__).resolve().parent.parent / 'static'

BG = (10, 13, 18)          # #0a0d12
BG2 = (15, 20, 28)         # #0f141c
CYAN = (63, 208, 224)      # #3fd0e0
VIOLET = (124, 92, 255)    # #7c5cff
TEXT = (232, 238, 246)     # #e8eef6
MUTED = (143, 161, 181)    # #8fa1b5

FONT_BOLD = Path(r'C:\Windows\Fonts\segoeuib.ttf')
FONT_REGULAR = Path(r'C:\Windows\Fonts\segoeui.ttf')
FONT_MONO = Path(r'C:\Windows\Fonts\consola.ttf')

SS = 4                     # supersampling factor


def lerp(a: tuple[int, int, int], b: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))


def vertical_gradient(size: tuple[int, int], top: tuple[int, int, int],
                      bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    grad = Image.new('RGB', (1, h))
    for y in range(h):
        grad.putpixel((0, y), lerp(top, bottom, y / max(1, h - 1)))
    return grad.resize((w, h), Image.BILINEAR)


def diagonal_gradient(size: tuple[int, int], a: tuple[int, int, int],
                      b: tuple[int, int, int]) -> Image.Image:
    w, h = size
    small = Image.new('RGB', (64, 64))
    for y in range(64):
        for x in range(64):
            small.putpixel((x, y), lerp(a, b, (x + y) / 126))
    return small.resize((w, h), Image.BICUBIC)


def rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0] - 1, size[1] - 1),
                                           radius=radius, fill=255)
    return mask


def mark(size: int, radius_ratio: float = 0.22) -> Image.Image:
    """The node-and-satellites mark on a rounded dark tile, at `size` px."""
    s = size * SS
    tile = Image.new('RGB', (s, s), BG)
    tile.paste(vertical_gradient((s, s), BG, BG2), (0, 0))
    tile.putalpha(rounded_mask((s, s), int(s * radius_ratio)))

    # the four satellites and the lines between them, as in static/icon.svg
    cx = cy = s / 2
    r = s * 0.25
    nodes = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)]
    lines = Image.new('RGBA', (s, s), (0, 0, 0, 0))
    ld = ImageDraw.Draw(lines)
    width = max(1, int(s * 0.0125))
    ring = [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy), (cx, cy - r)]
    ld.line(ring, fill=(*CYAN, 140), width=width, joint='curve')
    ld.line([(cx, cy - r), (cx, cy + r)], fill=(*VIOLET, 120), width=width)
    ld.line([(cx - r, cy), (cx + r, cy)], fill=(*VIOLET, 120), width=width)
    tile = Image.alpha_composite(tile.convert('RGBA'), lines)

    grad = diagonal_gradient((s, s), CYAN, VIOLET)
    dots = Image.new('L', (s, s), 0)
    dd = ImageDraw.Draw(dots)
    dot_r = s * 0.047
    for (x, y) in nodes:
        dd.ellipse((x - dot_r, y - dot_r, x + dot_r, y + dot_r), fill=255)
    tile.paste(grad, (0, 0), dots)

    # centre: dark disc with a gradient ring and a cyan core
    ring_layer = Image.new('L', (s, s), 0)
    ImageDraw.Draw(ring_layer).ellipse((cx - s * 0.068, cy - s * 0.068,
                                        cx + s * 0.068, cy + s * 0.068), outline=255,
                                       width=max(2, int(s * 0.018)))
    disc = Image.new('L', (s, s), 0)
    ImageDraw.Draw(disc).ellipse((cx - s * 0.058, cy - s * 0.058,
                                  cx + s * 0.058, cy + s * 0.058), fill=255)
    tile.paste(Image.new('RGBA', (s, s), (*BG, 255)), (0, 0), disc)
    tile.paste(grad, (0, 0), ring_layer)
    core = ImageDraw.Draw(tile)
    core.ellipse((cx - s * 0.024, cy - s * 0.024, cx + s * 0.024, cy + s * 0.024), fill=CYAN)

    return tile.resize((size, size), Image.LANCZOS)


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(str(path), size)
    except OSError:
        return ImageFont.load_default(size)


def radial_glow(width: int, height: int, cx: float, cy: float, radius: float,
                color: tuple[int, int, int], strength: int) -> Image.Image:
    """A soft radial falloff computed per pixel, with a little dither on the alpha."""
    rng = random.Random(7)
    layer = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    px = layer.load()
    for y in range(height):
        dy = y - cy
        for x in range(width):
            dx = x - cx
            d = math.hypot(dx, dy)
            if d >= radius:
                continue
            t = 1 - d / radius
            a = int(strength * t * t * t + rng.random() - 0.5)
            if a > 0:
                px[x, y] = (*color, min(255, a))
    return layer


def og_image() -> Image.Image:
    W, H = 1200, 630
    img = vertical_gradient((W, H), BG, BG2).convert('RGBA')

    img = Image.alpha_composite(img, radial_glow(W, H, 140, 10, 700, CYAN, 42))
    img = Image.alpha_composite(img, radial_glow(W, H, 1150, 0, 620, VIOLET, 46))

    # faint grid over everything, then the mark and the copy
    grid = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    grid_d = ImageDraw.Draw(grid)
    for x in range(0, W, 40):
        grid_d.line([(x, 0), (x, H)], fill=(255, 255, 255, 8))
    for y in range(0, H, 40):
        grid_d.line([(0, y), (W, y)], fill=(255, 255, 255, 8))
    img = Image.alpha_composite(img, grid)

    badge = mark(168, radius_ratio=0.26)
    img.paste(badge, (86, 92), badge)

    d = ImageDraw.Draw(img)
    d.text((86, 296), 'LearnLoop', font=font(FONT_BOLD, 92), fill=TEXT)
    d.text((92, 404), 'Plan it. Study it. Prove it.',
           font=font(FONT_REGULAR, 40), fill=MUTED)
    d.text((92, 474), 'Sessions · split PDFs · narrated lectures · auto-graded exercises',
           font=font(FONT_REGULAR, 27), fill=(128, 146, 166))

    # accent rule under the copy, echoing the app's progress bar
    bar = diagonal_gradient((560, 6), CYAN, VIOLET)
    img.paste(bar, (92, 540))

    d.text((92, 566), 'learnloop', font=font(FONT_MONO, 24), fill=(104, 122, 142))
    return img.convert('RGB')


def save_png(img: Image.Image, path: Path, colors: int | None = None) -> int:
    out = img
    if colors:
        # RGBA images only support the fast octree quantizer (keeps the rounded alpha)
        out = img.convert('RGBA').quantize(colors=colors, method=Image.FASTOCTREE,
                                           dither=Image.NONE)
    buf = io.BytesIO()
    out.save(buf, 'PNG', optimize=True)
    path.write_bytes(buf.getvalue())
    return len(buf.getvalue())


def main() -> None:
    STATIC.mkdir(parents=True, exist_ok=True)
    written = []

    written.append(('icon-192.png', save_png(mark(192), STATIC / 'icon-192.png', colors=128)))
    written.append(('icon-512.png', save_png(mark(512), STATIC / 'icon-512.png', colors=160)))
    # iOS applies its own mask, so this one is square with a small inset
    touch = mark(180, radius_ratio=0.0)
    written.append(('apple-touch-icon.png',
                    save_png(touch, STATIC / 'apple-touch-icon.png', colors=128)))

    ico_sizes = [16, 32, 48]
    icons = [mark(n, radius_ratio=0.2 if n > 20 else 0.0) for n in ico_sizes]
    icons[-1].save(STATIC / 'favicon.ico', format='ICO',
                   sizes=[(n, n) for n in ico_sizes])
    written.append(('favicon.ico', (STATIC / 'favicon.ico').stat().st_size))

    og = og_image()
    og_path = STATIC / 'og.jpg'
    og.save(og_path, 'JPEG', quality=90, optimize=True, progressive=True)
    written.append(('og.jpg', og_path.stat().st_size))
    stale = STATIC / 'og.png'
    if stale.exists():
        stale.unlink()             # the JPEG is a third of the size at the same quality

    for name, size in written:
        print(f'{name:22} {size / 1024:8.1f} KB')


if __name__ == '__main__':
    main()


