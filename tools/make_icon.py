"""生成程序图标 assets/app.ico。"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets" / "app.ico"


def draw(size: int) -> Image.Image:
    scale = size / 256
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    painter = ImageDraw.Draw(image)

    def s(value: float) -> float:
        return value * scale

    painter.rounded_rectangle(
        [s(8), s(8), s(248), s(248)], radius=s(56), fill=(47, 107, 255, 255)
    )
    # 上方的“黑板”
    painter.rounded_rectangle(
        [s(52), s(46), s(204), s(88)], radius=s(12), fill=(24, 34, 58, 255)
    )
    # 2x2 座位
    for row in range(2):
        for col in range(2):
            x = 52 + col * 78
            y = 106 + row * 62
            painter.rounded_rectangle(
                [s(x), s(y), s(x + 56), s(y + 44)], radius=s(12), fill=(255, 255, 255, 255)
            )
    return image


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = draw(256)
    base.save(OUT, format="ICO", sizes=[(size, size) for size in sizes])
    print("saved", OUT, OUT.stat().st_size)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
