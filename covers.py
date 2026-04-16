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


def generate_podcast_cover(out_path: Path, size: int = 1400,
                            tagline: str = "每晚 10 分钟 · AI 助眠") -> bool:
    """Render a square podcast cover for Apple Podcasts / Spotify / 小宇宙 submission.

    Apple requires 1400-3000 px square PNG/JPEG, <500KB, RGB, no transparency.
    This renders at 1400px (safe default) with large centered title + tagline +
    brand badge — same visual language as OG covers but in portrait-safe layout
    so it works as thumbnail in podcast catalog grids."""
    if not _HAS_PIL:
        return False
    rng = random.Random(_seed_from("podcast-cover"))

    # Gradient background
    img = Image.new("RGB", (size, size), (6, 6, 26))
    px = img.load()
    base_hue = 260 / 360.0
    warm_hue = 40 / 360.0
    for y in range(size):
        for x in range(size):
            # Diagonal blend with radial center dip
            t = (x + y) / (size * 2)
            dx = (x - size / 2) / size
            dy = (y - size / 2) / size
            r = (dx * dx + dy * dy) ** 0.5
            mid_weight = max(0.0, 1.0 - r * 1.8)
            c1 = _hsl_to_rgb(base_hue, 0.5, 0.14)
            c2 = _hsl_to_rgb(warm_hue, 0.6, 0.20)
            c0 = (6, 6, 26)
            gr = int(c1[0] * (1 - t) + c2[0] * t)
            gg = int(c1[1] * (1 - t) + c2[1] * t)
            gb = int(c1[2] * (1 - t) + c2[2] * t)
            rr = int(gr * (1 - mid_weight * 0.55) + c0[0] * (mid_weight * 0.55))
            rgg = int(gg * (1 - mid_weight * 0.55) + c0[1] * (mid_weight * 0.55))
            rb = int(gb * (1 - mid_weight * 0.55) + c0[2] * (mid_weight * 0.55))
            px[x, y] = (rr, rgg, rb)

    draw = ImageDraw.Draw(img, "RGBA")

    # Star field (denser than home cover — thumbnail visual richness)
    for _ in range(int(size / 8)):
        cx = rng.randint(0, size - 1)
        cy = rng.randint(0, size - 1)
        rad = rng.randint(1, max(2, size // 280))
        alpha = rng.randint(90, 220)
        draw.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(255, 255, 255, alpha))

    # Accent corner arcs
    draw.ellipse([size * 0.62, size * 0.62, size * 1.1, size * 1.1], fill=(124, 111, 247, 50))
    draw.ellipse([-size * 0.1, -size * 0.1, size * 0.3, size * 0.3], fill=(240, 194, 127, 35))

    # Badge (top)
    badge = "BEDTIME STORY"
    badge_font = _load_font(max(22, size // 40))
    try:
        bbox = draw.textbbox((0, 0), badge, font=badge_font)
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
    except AttributeError:
        bw, bh = draw.textsize(badge, font=badge_font)
    pad = size // 60
    bx1 = (size - bw) // 2 - pad * 2
    by1 = size // 5
    bx2 = bx1 + bw + pad * 4
    by2 = by1 + bh + pad * 2
    draw.rounded_rectangle([bx1, by1, bx2, by2], radius=size // 40,
                           fill=(124, 111, 247, 70),
                           outline=(124, 111, 247, 180), width=max(2, size // 600))
    draw.text((bx1 + pad * 2, by1 + pad - 4), badge, font=badge_font,
              fill=(240, 194, 127, 255))

    # Title (center, large)
    title = "助眠电台"
    title_font = _load_font(max(160, size // 6))
    try:
        bbox = draw.textbbox((0, 0), title, font=title_font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = (size - tw) // 2 - bbox[0]
        # Shift up slightly (title is visually heavy with descenders below baseline)
        ty = (size - th) // 2 - size // 20 - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(title, font=title_font)
        tx = (size - tw) // 2
        ty = (size - th) // 2 - size // 20
    # Soft shadow first
    draw.text((tx + 4, ty + 4), title, font=title_font, fill=(0, 0, 0, 120))
    draw.text((tx, ty), title, font=title_font, fill=(240, 240, 250, 255))

    # Tagline (under title)
    sub_font = _load_font(max(36, size // 28))
    try:
        bbox = draw.textbbox((0, 0), tagline, font=sub_font)
        sw = bbox[2] - bbox[0]
    except AttributeError:
        sw, _ = draw.textsize(tagline, font=sub_font)
    sx = (size - sw) // 2
    sy = ty + th + size // 30
    draw.text((sx, sy), tagline, font=sub_font, fill=(200, 200, 220, 230))

    # Footer "BEDTIME.FM" or GitHub URL — simple text at bottom
    footer = "bedtime.fm"  # aspirational placeholder
    footer_font = _load_font(max(22, size // 50))
    try:
        bbox = draw.textbbox((0, 0), footer, font=footer_font)
        fw = bbox[2] - bbox[0]
    except AttributeError:
        fw, _ = draw.textsize(footer, font=footer_font)
    draw.text(((size - fw) // 2, size - size // 12), footer,
              font=footer_font, fill=(160, 160, 190, 200))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return True


def generate_pwa_icon(out_path: Path, size: int = 512, maskable: bool = False) -> bool:
    """Generate a square PWA icon. When maskable=True, leaves extra padding so
    the icon survives being cropped to various round/square masks on different
    devices (PWA maskable icon spec)."""
    if not _HAS_PIL:
        return False
    rng = random.Random(_seed_from("pwa-icon"))
    # Diagonal gradient background
    img = Image.new("RGB", (size, size), (6, 6, 26))
    px = img.load()
    base_hue = 260 / 360.0
    warm_hue = 40 / 360.0
    for y in range(size):
        for x in range(size):
            t = (x + y) / (size * 2)
            c1 = _hsl_to_rgb(base_hue, 0.4, 0.18)
            c2 = _hsl_to_rgb(warm_hue, 0.5, 0.22)
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            px[x, y] = (r, g, b)

    draw = ImageDraw.Draw(img, "RGBA")
    # Stars
    for _ in range(int(size / 20)):
        cx = rng.randint(0, size - 1)
        cy = rng.randint(0, size - 1)
        rr = rng.randint(1, max(2, size // 200))
        alpha = rng.randint(80, 200)
        draw.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(255, 255, 255, alpha))

    # Accent arcs bottom-right
    draw.ellipse([size * 0.55, size * 0.55, size * 1.05, size * 1.05],
                 fill=(124, 111, 247, 45))
    draw.ellipse([size * 0.7, size * 0.7, size * 1.05, size * 1.05],
                 fill=(240, 194, 127, 30))

    # Centered Chinese character. Maskable icons need safe zone (~10% padding)
    safe_ratio = 0.75 if maskable else 0.88
    char = "眠"  # "sleep" — single iconic character
    font_size = int(size * safe_ratio * 0.72)
    font = _load_font(font_size)
    try:
        bbox = draw.textbbox((0, 0), char, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[0]
        # Use metrics offset to visually center
        cx = (size - tw) / 2 - bbox[0]
        cy = (size - th) / 2 - bbox[1]
    except AttributeError:
        tw, th = draw.textsize(char, font=font)
        cx = (size - tw) / 2
        cy = (size - th) / 2
    draw.text((cx, cy), char, font=font, fill=(240, 240, 250, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return True


if __name__ == "__main__":
    # smoke test
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/og_test.png")
    ok = generate_home_cover(out)
    print(f"cover: {out} {'OK' if ok else 'SKIPPED (no Pillow)'}")
