#!/usr/bin/env python3
"""把一张满幅方形插画处理成 macOS 标准风格的 .icns / .png 应用图标。

标准做法（参照系统应用图标）：
- 内容放在居中的圆角方形（squircle）内，四周留出透明边距
- 大圆角 + 高倍超采样抗锯齿，保证边缘平滑
- 底部加一层柔和投影，贴合 Dock 观感

用法:
  python3 make_icon.py [输入图片] [输出目录]
默认输入: assets/jardiff_icon_v2.png，输出图标到 jardiff_app/
"""

import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter

SIZE = 1024          # 画布
CONTENT = 824        # 内容区（四周各留 100 透明边距，符合 Apple 图标网格）
MARGIN = (SIZE - CONTENT) // 2
RADIUS = 185         # 824 内容区对应的圆角半径（≈ macOS squircle）
SS = 4               # 超采样倍数（抗锯齿）


def rounded_alpha(side: int, radius: int, ss: int) -> Image.Image:
    """生成带抗锯齿的圆角方形 alpha 蒙版。"""
    big = Image.new("L", (side * ss, side * ss), 0)
    d = ImageDraw.Draw(big)
    d.rounded_rectangle([0, 0, side * ss - 1, side * ss - 1],
                        radius=radius * ss, fill=255)
    return big.resize((side, side), Image.LANCZOS)


def make_png(src_path: str, out_png: str):
    img = Image.open(src_path).convert("RGBA")

    # 居中裁成正方形
    w, h = img.size
    s = min(w, h)
    img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    img = img.resize((CONTENT, CONTENT), Image.LANCZOS)

    # 套圆角
    img.putalpha(rounded_alpha(CONTENT, RADIUS, SS))

    canvas = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    # 柔和投影
    shadow_alpha = Image.new("L", (SIZE, SIZE), 0)
    sd = ImageDraw.Draw(shadow_alpha)
    sd.rounded_rectangle(
        [MARGIN, MARGIN + 10, MARGIN + CONTENT, MARGIN + CONTENT + 10],
        radius=RADIUS, fill=80,
    )
    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(20))
    black = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 255))
    canvas = Image.composite(black, canvas, shadow_alpha)

    # 贴内容
    canvas.paste(img, (MARGIN, MARGIN), img)
    canvas.save(out_png)
    print(f"  生成 {out_png} ({SIZE}x{SIZE})")


def make_icns(png_1024: str, out_icns: str):
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    names = {
        16: ("icon_16x16.png", None),
        32: ("icon_32x32.png", "icon_16x16@2x.png"),
        64: (None, "icon_32x32@2x.png"),
        128: ("icon_128x128.png", None),
        256: ("icon_256x256.png", "icon_128x128@2x.png"),
        512: ("icon_512x512.png", "icon_256x256@2x.png"),
        1024: (None, "icon_512x512@2x.png"),
    }
    base = Image.open(png_1024).convert("RGBA")
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, "JarDiff.iconset")
        os.makedirs(iconset)
        for sz in sizes:
            resized = base.resize((sz, sz), Image.LANCZOS)
            for nm in names[sz]:
                if nm:
                    resized.save(os.path.join(iconset, nm))
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out_icns], check=True)
    print(f"  生成 {out_icns}")


def make_ico(png_1024: str, out_ico: str):
    """生成 Windows 多尺寸 .ico（任务栏/桌面/exe 图标）。"""
    base = Image.open(png_1024).convert("RGBA")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48),
             (64, 64), (128, 128), (256, 256)]
    base.save(out_ico, format="ICO", sizes=sizes)
    print(f"  生成 {out_ico}")


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        root, "assets", "jardiff_icon_v2.png")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(root, "jardiff_app")

    if not os.path.isfile(src):
        print(f"找不到输入图片: {src}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(out_dir, exist_ok=True)
    png_1024 = os.path.join(out_dir, "icon_1024.png")
    icns = os.path.join(out_dir, "icon.icns")
    ico = os.path.join(out_dir, "icon.ico")

    print("处理图标…")
    make_png(src, png_1024)
    make_ico(png_1024, ico)
    # .icns 依赖 macOS 的 iconutil，仅在 mac 上生成
    if sys.platform == "darwin":
        make_icns(png_1024, icns)
    else:
        print("  跳过 .icns（仅 macOS 可生成）")
    print("完成")


if __name__ == "__main__":
    main()
