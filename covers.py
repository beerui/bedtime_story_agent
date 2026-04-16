#!/usr/bin/env python3
"""Generate OG social-share cover images for the podcast site.

每张 1200x630 PNG，匹配站点深色助眠主题：
  - 紫/金渐变背景，按 folder 名哈希偏色保证每期视觉唯一
  - 星点装饰
  - 中文标题（STHeiti Medium），主题徽章（较小字号），品牌名
  - 导出到 site/og/{folder}.png，用作 og:image / twitter:image

Pillow 缺失则本模块整体 no-op，调用方需自行判断 `available()`。

用法:
    from covers import available, generate_episode_cover, generate_home_cover
    if available():
        generate_episode_cover(episode_dict, out_path)
"""
from __future__ import annotations

import hashlib
import math
import os
import random
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    _HAS_PIL = True
except ImportError:
    _HAS_PIL = False

W, H = 1200, 630
BRAND = "助眠电台 · Bedtime Story Agent"

# macOS Chinese fonts, in order of preference. Extend for Linux/Windows CI use.
FONT_CANDIDATES = [
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
]

_font_cache: dict[tuple[str, int], "ImageFont.FreeTypeFont"] = {}


def available() -> bool:
    return _HAS_PIL


def _load_font(size: int) -> "ImageFont.FreeTypeFont | ImageFont.ImageFont":
    for path in FONT_CANDIDATES:
        if os.path.isfile(path):
            key = (path, size)
            if key not in _font_cache:
                try:
                    _font_cache[key] = ImageFont.truetype(path, size=size)
                except Exception:
                    continue
            return _font_cache[key]
    return ImageFont.load_default()


def _seed_from(name: str) -> int:
    return int(hashlib.sha1(name.encode("utf-8")).hexdigest()[:8], 16)


def _hsl_to_rgb(h: float, s: float, l: float) -> tuple[int, int, int]:
    """h in [0,1], s/l in [0,1]. Returns (r,g,b) ints."""
    if s == 0:
        v = int(l * 255)
        return (v, v, v)

    def hue2rgb(p: float, q: float, t: float) -> float:
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1 / 6: return p + (q - p) * 6 * t
        if t < 1 / 2: return q
        if t < 2 / 3: return p + (q - p) * (2 / 3 - t) * 6
        return p

    q = l * (1 + s) if l < 0.5 else l + s - l * s
    p = 2 * l - q
    r = hue2rgb(p, q, h + 1 / 3)
    g = hue2rgb(p, q, h)
    b = hue2rgb(p, q, h - 1 / 3)
    return (int(r * 255), int(g * 255), int(b * 255))


def _gradient_bg(seed: int) -> "Image.Image":
    """Diagonal gradient with per-episode color variation. Base hue hovers around
    the site's purple (260°) with ±30° drift seeded by episode name."""
    rng = random.Random(seed)
    base_hue = (260 + rng.randint(-30, 30)) % 360 / 360.0
    warm_hue = (40 + rng.randint(-10, 10)) % 360 / 360.0

    c_top = _hsl_to_rgb(base_hue, 0.45, 0.12)  # dark purple
    c_bot = _hsl_to_rgb(warm_hue, 0.55, 0.18)  # dark warm
    c_mid = (6, 6, 26)  # --bg-deep from site CSS

    img = Image.new("RGB", (W, H), c_mid)
    px = img.load()
    for y in range(H):
        # diagonal blend factor combining vertical + horizontal axes
        for x in range(W):
            t = (x + y * 0.6) / (W + H * 0.6)
            # radial dip in the middle toward c_mid for depth
            dx = (x - W / 2) / W
            dy = (y - H / 2) / H
            r = math.sqrt(dx * dx + dy * dy)
            mid_weight = max(0.0, 1.0 - r * 1.6)

            r1, g1, b1 = c_top
            r2, g2, b2 = c_bot
            r0, g0, b0 = c_mid
            # gradient component
            gr = int(r1 * (1 - t) + r2 * t)
            gg = int(g1 * (1 - t) + g2 * t)
            gb = int(b1 * (1 - t) + b2 * t)
            # mix with center darkness
            rr = int(gr * (1 - mid_weight * 0.5) + r0 * (mid_weight * 0.5))
            rg = int(gg * (1 - mid_weight * 0.5) + g0 * (mid_weight * 0.5))
            rb = int(gb * (1 - mid_weight * 0.5) + b0 * (mid_weight * 0.5))
            px[x, y] = (rr, rg, rb)
    return img


def _add_stars(img: "Image.Image", seed: int, count: int = 70) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    rng = random.Random(seed + 1)
    for _ in range(count):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        r = rng.randint(1, 3)
        alpha = rng.randint(60, 200)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255, alpha))


def _wrap_title(text: str, font: "ImageFont.FreeTypeFont", max_width: int) -> list[str]:
    """Simple char-by-char wrapping for Chinese. Returns ≤2 lines."""
    if not text:
        return [""]
    lines: list[str] = []
    buf = ""
    for ch in text:
        test = buf + ch
        w = font.getlength(test) if hasattr(font, "getlength") else len(test) * 30
        if w > max_width and buf:
            lines.append(buf)
            buf = ch
            if len(lines) >= 2:
                # truncate remainder with ellipsis on second line
                buf = lines[-1][:-1] + "…" if len(lines[-1]) > 1 else "…"
                return [lines[0], buf]
        else:
            buf = test
    lines.append(buf)
    return lines[:2]


def _text_size(draw: "ImageDraw.ImageDraw", text: str, font) -> tuple[int, int]:
    try:
        l, t, r, b = draw.textbbox((0, 0), text, font=font)
        return r - l, b - t
    except AttributeError:
        return draw.textsize(text, font=font)


def _render_cover(title: str, badge: str, subtitle: str, seed: int) -> "Image.Image":
    img = _gradient_bg(seed)
    _add_stars(img, seed)
    draw = ImageDraw.Draw(img, "RGBA")

    # badge (theme name) top-left
    badge_font = _load_font(32)
    if badge:
        bw, bh = _text_size(draw, badge, badge_font)
        pad_x, pad_y = 20, 12
        bg_x1, bg_y1 = 60, 70
        bg_x2, bg_y2 = bg_x1 + bw + pad_x * 2, bg_y1 + bh + pad_y * 2
        draw.rounded_rectangle(
            [bg_x1, bg_y1, bg_x2, bg_y2],
            radius=28,
            fill=(124, 111, 247, 60),
            outline=(124, 111, 247, 150),
            width=2,
        )
        draw.text((bg_x1 + pad_x, bg_y1 + pad_y - 2), badge, font=badge_font, fill=(240, 194, 127, 255))

    # title (main episode title)
    title_font = _load_font(84)
    title_lines = _wrap_title(title, title_font, max_width=W - 120)
    # compute total title block height and center vertically
    line_h = _text_size(draw, "助", title_font)[1] + 14
    block_h = line_h * len(title_lines)
    start_y = (H - block_h) // 2 - 20
    for i, line in enumerate(title_lines):
        draw.text((60, start_y + i * line_h), line, font=title_font, fill=(240, 240, 250, 255))

    # subtitle / tagline (below title)
    if subtitle:
        sub_font = _load_font(30)
        draw.text((60, start_y + block_h + 16), subtitle, font=sub_font, fill=(170, 170, 200, 255))

    # brand footer bottom-left
    brand_font = _load_font(26)
    draw.text((60, H - 70), BRAND, font=brand_font, fill=(140, 140, 180, 255))

    # accent corner arc (decorative)
    draw.ellipse([W - 160, H - 160, W + 40, H + 40], fill=(124, 111, 247, 40))
    draw.ellipse([W - 100, H - 100, W + 100, H + 100], fill=(240, 194, 127, 25))

    return img


def generate_episode_cover(ep: dict, out_path: Path) -> bool:
    """Render a cover for one episode. Returns True on success, False if Pillow unavailable."""
    if not _HAS_PIL:
        return False
    title = ep.get("title") or ep.get("theme") or "助眠故事"
    badge = ep.get("theme") or ""
    desc = (ep.get("description") or "").strip()
    subtitle = desc[:30] + "…" if len(desc) > 30 else desc
    seed = _seed_from(ep.get("folder", title))

    img = _render_cover(title, badge, subtitle, seed)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return True


def generate_home_cover(out_path: Path, tagline: str = "每晚 10 分钟 · AI 助眠 · 韵律弧线催眠") -> bool:
    """Render the site-wide flagship cover (homepage og:image)."""
    if not _HAS_PIL:
        return False
    img = _render_cover(
        title="助眠电台",
        badge="BEDTIME STORY",
        subtitle=tagline,
        seed=_seed_from("homepage"),
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return True


if __name__ == "__main__":
    # smoke test
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/og_test.png")
    ok = generate_home_cover(out)
    print(f"cover: {out} {'OK' if ok else 'SKIPPED (no Pillow)'}")
