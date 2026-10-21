"""Generate app and extension icons (Pillow required)."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "rapidgrab" / "assets"
EXT_ICONS = ROOT / "extension" / "icons"


def vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(image)
    for y in range(size):
        t = y / max(1, size - 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (size, y)], fill=color)
    return image


def render(size: int = 512) -> Image.Image:
    scale = size / 512
    image = vertical_gradient(size, (122, 162, 255), (59, 99, 232)).convert("RGBA")

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(112 * scale), fill=255
    )
    image.putalpha(mask)

    draw = ImageDraw.Draw(image)
    # Arrow shaft with rounded ends.
    shaft_width = int(44 * scale)
    draw.line(
        [(int(256 * scale), int(128 * scale)), (int(256 * scale), int(300 * scale))],
        fill=(255, 255, 255, 255),
        width=shaft_width,
    )
    radius = shaft_width // 2
    for cy in (int(128 * scale), int(300 * scale)):
        cx = int(256 * scale)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), fill=(255, 255, 255, 255))
    # Arrow head.
    draw.polygon(
        [
            (int(158 * scale), int(244 * scale)),
            (int(256 * scale), int(348 * scale)),
            (int(354 * scale), int(244 * scale)),
        ],
        fill=(255, 255, 255, 255),
    )
    # Base bar.
    draw.rounded_rectangle(
        (int(140 * scale), int(396 * scale), int(372 * scale), int(438 * scale)),
        radius=int(21 * scale),
        fill=(255, 255, 255, 235),
    )
    return image


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    EXT_ICONS.mkdir(parents=True, exist_ok=True)
    master = render(512)
    master.save(ASSETS / "app_icon.png")
    master.save(ROOT / "build" / "icon_512.png")
    master.save(
        ASSETS / "rapidgrab.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    for dimension in (16, 32, 48, 128):
        icon = master.resize((dimension, dimension), Image.Resampling.LANCZOS)
        icon.save(EXT_ICONS / f"icon{dimension}.png")
    print(f"Wrote icons to {ASSETS} and {EXT_ICONS}")


if __name__ == "__main__":
    main()
