#!/usr/bin/env python3
"""从已生产内容生成播客订阅源和深色主题在线播放器。

将 outputs/ 目录中的音频、字幕、元数据打包为：
  site/index.html  — 深色助眠主题播放器（睡眠定时、字幕同步）
  site/feed.xml    — Podcast RSS 2.0 订阅源（兼容 Apple Podcasts / Spotify）

用法:
    python3 publish.py                      # 生成到 site/
    python3 publish.py --serve              # 生成 + 启动本地服务器 + 打开浏览器
    python3 publish.py --base-url URL       # 设置音频 URL 前缀（用于公网部署）
"""
import argparse
import datetime
import html as html_mod
import http.server
import json
import os
import shutil
import struct
import textwrap
import threading
import webbrowser
import xml.etree.ElementTree as ET
from email.utils import formatdate
from pathlib import Path

try:
    import covers as _covers
except Exception:
    _covers = None

try:
    import audio_tags as _audio_tags
except Exception:
    _audio_tags = None

try:
    from config import THEMES as _THEMES, THEME_CATEGORIES as _THEME_CATEGORIES
except Exception:
    _THEMES = {}
    _THEME_CATEGORIES = {}

ROOT_DIR = Path(__file__).parent
OUTPUTS_DIR = ROOT_DIR / "outputs"
SITE_DIR = ROOT_DIR / "site"
MONETIZATION_PATH = ROOT_DIR / "monetization.json"
MONETIZATION_EXAMPLE_PATH = ROOT_DIR / "monetization.example.json"

PODCAST_TITLE = "助眠电台 · Bedtime Story Agent"
PODCAST_DESC = "全自动 AI 助眠音频——从文字到可发布的成品，每一期都是独一无二的深度睡眠旅程。"
PODCAST_AUTHOR = "Bedtime Story Agent"
PODCAST_LANG = "zh-cn"
PODCAST_CATEGORY = "Health &amp; Fitness"


def load_monetization() -> dict:
    """Load monetization.json if present; fall back to the example template."""
    for path in (MONETIZATION_PATH, MONETIZATION_EXAMPLE_PATH):
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[warn] 无法解析 {path.name}: {e}")
    return {}


# ---------------------------------------------------------------------------
# MP3 duration estimation (no external deps)
# ---------------------------------------------------------------------------

_MP3_BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
_MP3_SAMPLE_RATES_V1 = [44100, 48000, 32000, 0]


def _estimate_mp3_duration(filepath: str) -> int:
    """Estimate MP3 duration in seconds by reading frame headers.
    Falls back to file-size estimate at 128 kbps."""
    size = os.path.getsize(filepath)
    try:
        with open(filepath, "rb") as f:
            header_bytes = f.read(4096)
        # skip ID3v2 tag if present
        offset = 0
        if header_bytes[:3] == b"ID3":
            tag_size = (
                (header_bytes[6] & 0x7F) << 21
                | (header_bytes[7] & 0x7F) << 14
                | (header_bytes[8] & 0x7F) << 7
                | (header_bytes[9] & 0x7F)
            )
            offset = 10 + tag_size
            with open(filepath, "rb") as f:
                f.seek(offset)
                header_bytes = f.read(4)
        else:
            header_bytes = header_bytes[:4]
            for i in range(min(len(header_bytes) - 1, 4096)):
                if header_bytes[i] == 0xFF and (header_bytes[i + 1] & 0xE0) == 0xE0:
                    header_bytes = header_bytes[i : i + 4]
                    break

        if len(header_bytes) >= 4 and header_bytes[0] == 0xFF and (header_bytes[1] & 0xE0) == 0xE0:
            bitrate_idx = (header_bytes[2] >> 4) & 0x0F
            sr_idx = (header_bytes[2] >> 2) & 0x03
            bitrate = _MP3_BITRATES_V1_L3[bitrate_idx] * 1000
            if bitrate > 0:
                return int(size * 8 / bitrate)
    except Exception:
        pass
    # fallback: assume 128 kbps
    return int(size * 8 / 128000)


# ---------------------------------------------------------------------------
# Episode scanning
# ---------------------------------------------------------------------------

def scan_episodes(outputs_dir: Path) -> list[dict]:
    """Scan outputs/ and return episode metadata sorted newest-first."""
    episodes = []
    if not outputs_dir.is_dir():
        return episodes

    for folder in sorted(outputs_dir.iterdir(), reverse=True):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        audio = folder / "final_audio.mp3"
        if not audio.is_file():
            continue

        # metadata
        meta = {}
        meta_path = folder / "metadata.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                pass

        # story draft
        draft = folder / "story_draft.txt"
        draft_text = ""
        word_count = 0
        if draft.is_file():
            draft_text = draft.read_text(encoding="utf-8")
            word_count = len(draft_text)

        # SRT subtitles
        srt_path = folder / "subtitles.srt"
        srt_text = ""
        if srt_path.is_file():
            srt_text = srt_path.read_text(encoding="utf-8")

        # extract theme from folder name: Batch_YYYYMMDD_HHMMSS_主题
        parts = folder.name.split("_", 3)
        theme = parts[3] if len(parts) >= 4 else folder.name

        # timestamp from folder name
        try:
            ts = datetime.datetime.strptime(
                f"{parts[1]}_{parts[2]}", "%Y%m%d_%H%M%S"
            )
        except (ValueError, IndexError):
            ts = datetime.datetime.fromtimestamp(audio.stat().st_mtime)

        duration = _estimate_mp3_duration(str(audio))

        episodes.append(
            {
                "folder": folder.name,
                "theme": theme,
                "title": meta.get("title", theme),
                "description": meta.get("description_xiaoyuzhou", meta.get("description_ximalaya", "")),
                "tags": meta.get("tags", []),
                "audio_path": str(audio.relative_to(outputs_dir.parent)),
                "audio_abs": str(audio),
                "audio_size": audio.stat().st_size,
                "duration": duration,
                "word_count": word_count,
                "draft": draft_text[:500],
                "draft_full": draft_text,
                "srt": srt_text,
                "timestamp": ts,
                "pub_date": formatdate(ts.timestamp(), localtime=True),
            }
        )
    return episodes


# ---------------------------------------------------------------------------
# Audio deployment (self-contained site)
# ---------------------------------------------------------------------------

def deploy_audio(episodes: list[dict], site_dir: Path) -> None:
    """Copy all episode audio into site/audio/ and set ep['site_audio'] to the
    relative path inside site/. This makes the site self-contained — deployable
    to GitHub Pages / Vercel / Netlify without needing outputs/ alongside.

    Also embeds ID3 tags + CHAP chapters (if mutagen installed) so podcast apps
    like Apple Podcasts / Pocket Casts / Overcast can show chapter markers."""
    audio_out = site_dir / "audio"
    audio_out.mkdir(parents=True, exist_ok=True)
    tagged = 0
    for ep in episodes:
        dest_name = f"{ep['folder']}.mp3"
        dest = audio_out / dest_name
        src = Path(ep["audio_abs"])
        needs_copy = not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime
        if needs_copy:
            shutil.copy2(src, dest)
        ep["site_audio"] = f"audio/{dest_name}"

        # Embed ID3 tags + chapters once per (re)copied file
        if needs_copy and _audio_tags and _audio_tags.available():
            chapters = extract_chapters(ep.get("draft_full", ""), ep.get("srt", ""))
            ok = _audio_tags.embed_episode_metadata(
                str(dest),
                title=ep.get("title") or ep.get("theme") or "助眠故事",
                artist=PODCAST_AUTHOR,
                album=PODCAST_TITLE,
                comment=(ep.get("description") or "")[:500],
                year=ep["timestamp"].strftime("%Y"),
                chapters=chapters or None,
            )
            if ok:
                tagged += 1
    if tagged:
        print(f"[OK] ID3 标签 + 章节嵌入 × {tagged} 个 MP3")


def resolve_html_audio(ep: dict) -> str:
    """Path for the <audio> src in the generated HTML (relative to site/index.html)."""
    if ep.get("site_audio"):
        return ep["site_audio"]
    return f"../{ep['audio_path']}"


def resolve_rss_audio(ep: dict, base_url: str) -> str:
    """Absolute URL for the RSS <enclosure>."""
    rel = ep.get("site_audio") or ep["audio_path"]
    if base_url:
        return f"{base_url.rstrip('/')}/{rel}"
    return rel


# ---------------------------------------------------------------------------
# RSS feed generation
# ---------------------------------------------------------------------------

def generate_rss(episodes: list[dict], base_url: str) -> str:
    """Generate a Podcast RSS 2.0 XML feed."""
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("content", CONTENT_NS)

    rss = ET.Element("rss", version="2.0")

    channel = ET.SubElement(rss, "channel")
    ET.SubElement(channel, "title").text = PODCAST_TITLE
    ET.SubElement(channel, "description").text = PODCAST_DESC
    ET.SubElement(channel, "language").text = PODCAST_LANG
    ET.SubElement(channel, "link").text = base_url or "https://example.com"
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = PODCAST_AUTHOR
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "no"
    cat = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    cat.set("text", "Health & Fitness")

    for ep in episodes:
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "description").text = ep["description"]
        ET.SubElement(item, "pubDate").text = ep["pub_date"]

        audio_url = resolve_rss_audio(ep, base_url)
        enc = ET.SubElement(item, "enclosure")
        enc.set("url", audio_url)
        enc.set("length", str(ep["audio_size"]))
        enc.set("type", "audio/mpeg")

        dur = ET.SubElement(item, "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration")
        m, s = divmod(ep["duration"], 60)
        dur.text = f"{m}:{s:02d}"

        ET.SubElement(item, "guid", isPermaLink="false").text = ep["folder"]

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")


# ---------------------------------------------------------------------------
# HTML player generation
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def _build_subscribe_html(m: dict, feed_url: str) -> str:
    """Subscription buttons row — the primary CTA on the homepage.

    Renders RSS + 复制 RSS always; platform buttons only when their URL is set
    in monetization.json → subscribe.{platform}_url."""
    sub = (m or {}).get("subscribe") or {}
    feed_url = feed_url or "feed.xml"
    # Apple Podcasts: prefer explicit URL; otherwise auto-generate podcasts:// only when
    # feed_url looks like a real site (not the placeholder 你的域名.com)
    podcasts_href = sub.get("apple_podcasts_url") or ""
    if not podcasts_href and feed_url.startswith(("http://", "https://")):
        if "你的域名" not in feed_url and "example.com" not in feed_url:
            podcasts_href = "podcasts://" + feed_url.split("://", 1)[1]

    buttons: list[str] = []
    if podcasts_href:
        buttons.append(
            f'<a class="sub-btn sub-apple" href="{_esc(podcasts_href)}" target="_blank" rel="noopener">'
            f'<span class="sub-logo">🎧</span><span class="sub-label">Apple Podcasts</span></a>'
        )
    if sub.get("spotify_url"):
        buttons.append(
            f'<a class="sub-btn sub-spotify" href="{_esc(sub["spotify_url"])}" target="_blank" rel="noopener">'
            f'<span class="sub-logo">🎵</span><span class="sub-label">Spotify</span></a>'
        )
    if sub.get("xiaoyuzhou_url"):
        buttons.append(
            f'<a class="sub-btn sub-xyz" href="{_esc(sub["xiaoyuzhou_url"])}" target="_blank" rel="noopener">'
            f'<span class="sub-logo">🌙</span><span class="sub-label">小宇宙</span></a>'
        )
    if sub.get("overcast_url"):
        buttons.append(
            f'<a class="sub-btn sub-overcast" href="{_esc(sub["overcast_url"])}" target="_blank" rel="noopener">'
            f'<span class="sub-logo">🔆</span><span class="sub-label">Overcast</span></a>'
        )
    if sub.get("bilibili_url"):
        buttons.append(
            f'<a class="sub-btn sub-bili" href="{_esc(sub["bilibili_url"])}" target="_blank" rel="noopener">'
            f'<span class="sub-logo">📺</span><span class="sub-label">Bilibili</span></a>'
        )
    # always show RSS + copy
    buttons.append(
        f'<a class="sub-btn sub-rss" href="{_esc(feed_url)}" target="_blank" rel="noopener">'
        f'<span class="sub-logo">📡</span><span class="sub-label">RSS</span></a>'
    )
    buttons.append(
        f"<button class=\"sub-btn sub-copy\" onclick='copyFeed(this, {json.dumps(feed_url, ensure_ascii=False)})'>"
        f'<span class="sub-logo">📋</span><span class="sub-label">复制 RSS</span></button>'
    )

    hint = sub.get("hint") or "订阅后每期新内容会自动推送到你的播客 App"
    return textwrap.dedent(f"""
    <section class="subscribe">
      <div class="sub-title">订阅收听</div>
      <div class="sub-row">
        {''.join(buttons)}
      </div>
      <div class="sub-hint">{_esc(hint)}</div>
    </section>""")


def _build_support_html(m: dict) -> str:
    """Render the 支持电台 block (donation / sponsor / affiliates / premium)."""
    if not m:
        return ""
    parts: list[str] = []

    don = m.get("donation") or {}
    if don.get("enabled") and don.get("url"):
        note = _esc(don.get("note", ""))
        parts.append(f"""
      <a class="support-tile support-donation" href="{_esc(don['url'])}" target="_blank" rel="noopener">
        <div class="support-icon">{_esc(don.get('icon','☕'))}</div>
        <div class="support-body">
          <div class="support-title">{_esc(don.get('label','支持我们'))}</div>
          <div class="support-note">{note}</div>
        </div>
      </a>""")

    spon = m.get("sponsor_slot") or {}
    if spon.get("enabled"):
        url = spon.get("url", "")
        href_attr = f' href="{_esc(url)}"' if url else ""
        tag = "a" if url else "div"
        parts.append(f"""
      <{tag} class="support-tile support-sponsor"{href_attr} target="_blank" rel="noopener">
        <div class="support-icon">💫</div>
        <div class="support-body">
          <div class="support-title">{_esc(spon.get('label','本期赞助位'))}</div>
          <div class="support-note">{_esc(spon.get('text',''))}</div>
        </div>
      </{tag}>""")

    prem = m.get("premium") or {}
    if prem.get("enabled") and prem.get("url"):
        parts.append(f"""
      <a class="support-tile support-premium" href="{_esc(prem['url'])}" target="_blank" rel="noopener">
        <div class="support-icon">🌙</div>
        <div class="support-body">
          <div class="support-title">{_esc(prem.get('label','会员专享'))}</div>
          <div class="support-note">{_esc(prem.get('price_note',''))}</div>
        </div>
      </a>""")

    tiles = "\n".join(parts)

    aff = m.get("affiliates") or {}
    aff_html = ""
    if aff.get("enabled") and aff.get("items"):
        item_cards = []
        for it in aff["items"]:
            if not it.get("url"):
                continue
            item_cards.append(f"""
        <a class="aff-card" href="{_esc(it['url'])}" target="_blank" rel="nofollow sponsored noopener">
          <div class="aff-emoji">{_esc(it.get('emoji','🛒'))}</div>
          <div class="aff-title">{_esc(it.get('title',''))}</div>
          <div class="aff-desc">{_esc(it.get('desc',''))}</div>
        </a>""")
        if item_cards:
            aff_html = f"""
    <section class="affiliates">
      <div class="aff-header">
        <h2>{_esc(aff.get('title','听众的小装备'))}</h2>
        <p class="aff-disclaimer">{_esc(aff.get('disclaimer',''))}</p>
      </div>
      <div class="aff-grid">{''.join(item_cards)}</div>
    </section>"""

    if not tiles and not aff_html:
        return ""

    tiles_section = f"""
    <section class="support">
      <h2>支持这个电台</h2>
      <div class="support-grid">{tiles}</div>
    </section>""" if tiles else ""

    return tiles_section + aff_html


def _build_placeholder_html(base_url: str) -> str:
    """Minimal self-contained landing page for when outputs/ is empty.

    Used on first deployment when no episode has been produced yet — ensures the
    GitHub Pages pipeline succeeds and the user gets a visible page explaining
    what went wrong and what to do next."""
    site_url = (base_url or "").rstrip("/")
    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{PODCAST_TITLE} · 准备中</title>
    <meta name="description" content="{PODCAST_DESC}">
    <meta name="robots" content="noindex">
    <style>
      body {{
        background: #06061a; color: #d4d4e0;
        font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
        display: flex; align-items: center; justify-content: center;
        min-height: 100vh; margin: 0; padding: 20px; text-align: center;
      }}
      .wrap {{ max-width: 520px; }}
      h1 {{
        font-size: 1.8rem; margin-bottom: 20px;
        background: linear-gradient(135deg, #f0c27f, #7c6ff7);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      }}
      p {{ line-height: 1.8; color: #9a9ab0; margin-bottom: 14px; }}
      code {{
        background: rgba(255,255,255,0.06);
        padding: 2px 8px; border-radius: 6px;
        font-family: ui-monospace, "SF Mono", Menlo, monospace;
        color: #f0c27f;
      }}
      ol {{ text-align: left; color: #9a9ab0; line-height: 2; padding-left: 1.2em; }}
      .dot {{
        display: inline-block; width: 8px; height: 8px;
        background: #f0c27f; border-radius: 50%;
        animation: pulse 1.6s ease-in-out infinite alternate;
        margin-right: 6px; vertical-align: middle;
      }}
      @keyframes pulse {{ 0% {{ opacity: 0.3; }} 100% {{ opacity: 1; }} }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <h1>助眠电台 · 准备中</h1>
        <p><span class="dot"></span>站点已部署，但还没有节目内容。</p>
        <p>通常是因为生产环节没能产出音频。最常见原因：</p>
        <ol>
          <li><code>DASHSCOPE_API_KEY</code> 没配在 Secrets 里</li>
          <li>API 配额耗尽（<code>batch.py</code> 会降级到 edge-tts，但仍需 Qwen 生成文本）</li>
          <li>workflow 首次运行时 <code>content</code> 分支不存在（正常，下次会建立）</li>
        </ol>
        <p>查看 Actions 标签页最新一次运行的日志，定位失败的 step。</p>
      </div>
    </body>
    </html>
    """)


def _build_head_meta(episodes: list[dict], m: dict, base_url: str, cover_rel: str = "og/home.png") -> str:
    site_url = (base_url or (m or {}).get("site_url") or "").rstrip("/")
    tagline = _esc(m.get("brand_tagline") or PODCAST_DESC)
    og_url = site_url or ""
    feed_url = f"{site_url}/feed.xml" if site_url else "feed.xml"
    og_image = f"{site_url}/{cover_rel}" if site_url else cover_rel

    jsonld = {
        "@context": "https://schema.org",
        "@type": "PodcastSeries",
        "name": PODCAST_TITLE,
        "description": PODCAST_DESC,
        "inLanguage": PODCAST_LANG,
        "author": {"@type": "Person", "name": PODCAST_AUTHOR},
        "webFeed": feed_url,
    }
    if site_url:
        jsonld["url"] = site_url
        jsonld["image"] = og_image
    if episodes:
        jsonld["numberOfEpisodes"] = len(episodes)

    return textwrap.dedent(f"""\
    <meta name="description" content="{tagline}">
    <meta name="keywords" content="助眠,睡眠,冥想,ASMR,白噪音,催眠,播客,深度睡眠">
    <meta name="author" content="{_esc(PODCAST_AUTHOR)}">
    <meta property="og:type" content="website">
    <meta property="og:title" content="{_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="{tagline}">
    <meta property="og:site_name" content="{_esc(PODCAST_TITLE)}">
    <meta property="og:locale" content="zh_CN">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    {'<meta property="og:url" content="' + _esc(og_url) + '">' if og_url else ''}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{_esc(PODCAST_TITLE)}">
    <meta name="twitter:description" content="{tagline}">
    <meta name="twitter:image" content="{_esc(og_image)}">
    <link rel="alternate" type="application/rss+xml" title="{_esc(PODCAST_TITLE)} RSS" href="{_esc(feed_url)}">
    <script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
    {_build_analytics_head(m)}""")


import re


_PHASE_RE = re.compile(r"\[阶段[:：]\s*([^\]]+)\]")
_PAUSE_RE = re.compile(r"\[停顿[^\]]*\]")
_CUE_RE = re.compile(r"\[环境音[:：]\s*([^\]]+)\]")
_STRIP_RE = re.compile(r"\[[^\]]+\]")


def render_script_html(text: str) -> str:
    """Turn a story draft (with prosody/phase/cue markup) into readable HTML.

    Phase markers become section headings, pauses become paragraph breaks,
    ambient cues become inline parentheticals, all other bracket tags are stripped."""
    if not text:
        return ""

    sections: list[tuple[str, list[str]]] = []  # (phase_name, paragraphs)
    current_phase = ""
    current_paragraphs: list[str] = []
    current_buf: list[str] = []

    def flush_paragraph():
        line = "".join(current_buf).strip()
        current_buf.clear()
        if line:
            current_paragraphs.append(line)

    def flush_section():
        flush_paragraph()
        if current_paragraphs:
            sections.append((current_phase, list(current_paragraphs)))
            current_paragraphs.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush_paragraph()
            continue

        phase_m = _PHASE_RE.match(line)
        if phase_m:
            flush_section()
            current_phase = phase_m.group(1).strip()
            continue

        # replace cues inline with italic parenthetical
        line = _CUE_RE.sub(lambda m: f"__CUE__{m.group(1).strip()}__ECUE__", line)
        # strip pauses (they force paragraph breaks)
        parts = _PAUSE_RE.split(line)
        for idx, seg in enumerate(parts):
            clean = _STRIP_RE.sub("", seg).strip()
            if clean:
                current_buf.append(clean)
            if idx < len(parts) - 1:
                flush_paragraph()

    flush_section()

    # render to HTML
    html_parts: list[str] = []
    for phase, paras in sections:
        if phase:
            html_parts.append(f'<h2 class="phase">{_esc(phase)}</h2>')
        for p in paras:
            safe = _esc(p)
            safe = safe.replace("__CUE__", '<em class="cue">（').replace("__ECUE__", "）</em>")
            html_parts.append(f"<p>{safe}</p>")
    return "\n".join(html_parts)


def _episode_slug(ep: dict) -> str:
    return ep["folder"]


_SRT_BLOCK_RE = re.compile(
    r"(\d+):(\d+):(\d+)[,\.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,\.](\d+)"
)


def extract_chapters(story_text: str, srt_text: str) -> list[dict]:
    """Build chapter list by correlating [阶段：X] markers in the story with
    SRT cue timestamps. Returns [{title, start_sec, end_sec}]. Empty list if
    either input is missing or no phases detected.

    Strategy:
      - Parse SRT into ordered cues (start_sec, end_sec)
      - Walk story lines; narrative lines correspond 1:1 with cues in order
      - When a [阶段：X] marker precedes the next narrative line, that line's
        cue start_sec becomes the chapter start."""
    if not story_text or not srt_text:
        return []

    cues: list[tuple[float, float]] = []
    for block in re.split(r"\n\n+", srt_text.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        m = _SRT_BLOCK_RE.search(lines[1]) if len(lines) >= 2 else None
        if not m:
            continue
        start = int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3]) + int(m[4]) / 1000
        end = int(m[5]) * 3600 + int(m[6]) * 60 + int(m[7]) + int(m[8]) / 1000
        cues.append((start, end))

    if not cues:
        return []

    # Walk story lines; track which cue index each phase starts at
    phase_starts: list[tuple[str, int]] = []
    pending_phase: str | None = None
    cue_idx = 0
    for raw in story_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        phase_m = _PHASE_RE.match(line)
        if phase_m:
            pending_phase = phase_m.group(1).strip()
            continue
        # Strip all bracket tags — if the line becomes empty it had no narrative
        narrative = _STRIP_RE.sub("", line).strip()
        if not narrative:
            continue
        if cue_idx >= len(cues):
            break
        if pending_phase is not None:
            phase_starts.append((pending_phase, cue_idx))
            pending_phase = None
        cue_idx += 1

    if not phase_starts:
        return []

    chapters: list[dict] = []
    last_end = cues[-1][1]
    for i, (name, idx) in enumerate(phase_starts):
        start = cues[idx][0]
        if i + 1 < len(phase_starts):
            next_idx = phase_starts[i + 1][1]
            end = cues[next_idx][0] if next_idx < len(cues) else last_end
        else:
            end = last_end
        chapters.append({"title": name, "start_sec": start, "end_sec": end})
    return chapters


def _episode_href(ep: dict) -> str:
    """Link path from site/index.html to the episode page."""
    return f"episodes/{_episode_slug(ep)}.html"


def _build_analytics_head(m: dict) -> str:
    """Render optional analytics snippets from monetization.json.

    Supports Plausible (privacy-first, recommended), Umami (self-hosted), and GA4."""
    a = (m or {}).get("analytics") or {}
    out: list[str] = []
    plausible = (a.get("plausible_domain") or "").strip()
    if plausible:
        out.append(f'<script defer data-domain="{_esc(plausible)}" src="https://plausible.io/js/script.js"></script>')
    umami_url = (a.get("umami_script_url") or "").strip()
    umami_id = (a.get("umami_website_id") or "").strip()
    if umami_url and umami_id:
        out.append(f'<script defer src="{_esc(umami_url)}" data-website-id="{_esc(umami_id)}"></script>')
    ga = (a.get("google_analytics_id") or "").strip()
    if ga:
        out.append(f'<script async src="https://www.googletagmanager.com/gtag/js?id={_esc(ga)}"></script>')
        out.append(
            '<script>window.dataLayer=window.dataLayer||[];function gtag(){dataLayer.push(arguments);}'
            f'gtag("js",new Date());gtag("config","{_esc(ga)}");</script>'
        )
    return "\n    ".join(out)


def _related_episodes(target: dict, all_eps: list[dict], k: int = 3) -> list[dict]:
    """Pick up to k episodes most similar to `target` by tag overlap.
    Falls back to nearest-in-time when no tag overlap exists."""
    target_tags = set(target.get("tags") or [])
    target_folder = target["folder"]
    scored: list[tuple[int, int, dict]] = []
    for ep in all_eps:
        if ep["folder"] == target_folder:
            continue
        overlap = len(target_tags & set(ep.get("tags") or []))
        time_delta = abs((ep["timestamp"] - target["timestamp"]).total_seconds())
        # higher overlap first, then closer in time (negative so sorts ascending)
        scored.append((-overlap, time_delta, ep))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored[:k]]


def generate_episode_page(ep: dict, monetization: dict, base_url: str, total_eps: int,
                          prev_ep: dict | None = None, next_ep: dict | None = None,
                          related: list[dict] | None = None) -> str:
    """Standalone long-form page for one episode — optimized for SEO long-tail traffic.

    Contains full readable transcript, embedded audio, share buttons, and
    episode-specific OG/JSON-LD metadata so social shares and search engines
    get proper previews."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    page_path = f"episodes/{_episode_slug(ep)}.html"
    canonical = f"{site_url}/{page_path}" if site_url else page_path
    # audio path: episode pages live in site/episodes/, audio in site/audio/ → ../audio/
    audio_src = f"../audio/{ep['folder']}.mp3" if ep.get("site_audio") else f"../../{ep['audio_path']}"
    audio_abs = f"{site_url}/audio/{ep['folder']}.mp3" if site_url and ep.get("site_audio") else ""
    # OG cover: per-episode PNG in site/og/; from episodes/*.html it's ../og/
    cover_rel = f"og/{ep['folder']}.png"
    og_image = f"{site_url}/{cover_rel}" if site_url else f"../{cover_rel}"

    desc_plain = ep["description"] or (ep["draft_full"][:140] + "…" if len(ep["draft_full"]) > 140 else ep["draft_full"])
    desc_plain = _STRIP_RE.sub("", desc_plain).strip()

    jsonld_ep = {
        "@context": "https://schema.org",
        "@type": "PodcastEpisode",
        "name": ep["title"],
        "description": desc_plain[:500],
        "datePublished": ep["timestamp"].strftime("%Y-%m-%d"),
        "inLanguage": PODCAST_LANG,
        "duration": f"PT{ep['duration'] // 60}M{ep['duration'] % 60}S",
        "partOfSeries": {"@type": "PodcastSeries", "name": PODCAST_TITLE},
    }
    if audio_abs:
        jsonld_ep["associatedMedia"] = {
            "@type": "MediaObject",
            "contentUrl": audio_abs,
            "encodingFormat": "audio/mpeg",
        }

    transcript_html = render_script_html(ep["draft_full"])
    tags_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in ep["tags"][:6])

    # SEO: combine theme-level search_keywords (from config) + episode tags (from metadata.json)
    # Theme keywords target the search intent; episode tags are content-specific.
    theme_cfg = _THEMES.get(ep["theme"]) or {}
    theme_keywords = theme_cfg.get("search_keywords") or []
    category_key = theme_cfg.get("category")
    category_cfg = _THEME_CATEGORIES.get(category_key) if category_key else None
    category_keywords = category_cfg.get("seo_keywords", []) if category_cfg else []
    # dedup while preserving order
    seen = set()
    keywords: list[str] = []
    for kw in [*theme_keywords, *category_keywords, *ep["tags"], "助眠", "睡眠", "冥想"]:
        k = kw.strip()
        if k and k not in seen:
            seen.add(k)
            keywords.append(k)
    keywords_meta = ",".join(keywords[:12])

    share_text = f"{ep['title']} | {PODCAST_TITLE}"
    analytics_head = _build_analytics_head(m)

    # Chapters — one per [阶段：X] marker. Renders as clickable navigation below
    # the player so returning listeners can jump to e.g. the body-scan section.
    chapters = extract_chapters(ep.get("draft_full", ""), ep.get("srt", ""))
    chapters_html = ""
    if chapters:
        chapter_items = []
        for i, ch in enumerate(chapters):
            dur = int(ch["end_sec"] - ch["start_sec"])
            start_str = _fmt_duration(int(ch["start_sec"]))
            chapter_items.append(
                f'<button class="chapter" data-start="{ch["start_sec"]:.2f}" data-idx="{i}" '
                f'data-track="Jump Chapter" data-prop-name="{_esc(ch["title"])}">'
                f'<span class="chapter-time">{start_str}</span>'
                f'<span class="chapter-name">{_esc(ch["title"])}</span>'
                f'<span class="chapter-dur">{dur // 60}:{dur % 60:02d}</span>'
                f'</button>'
            )
        chapters_html = (
            '<nav class="chapters" aria-label="章节导航">'
            + "".join(chapter_items)
            + "</nav>"
        )

    # Clinical technique badge — surfaces pain_point / technique for trust-building.
    # Skipped silently when theme has no metadata (custom themes or legacy config).
    tech_badge_html = ""
    pp = theme_cfg.get("pain_point", "").strip()
    tech = theme_cfg.get("technique", "").strip()
    target = theme_cfg.get("emotional_target", "").strip()
    if pp or tech:
        rows = []
        if pp:
            rows.append(f'<div class="tech-row"><span class="tech-label">此刻的感受</span><span class="tech-val">{_esc(pp)}</span></div>')
        if tech:
            rows.append(f'<div class="tech-row"><span class="tech-label">使用的技术</span><span class="tech-val">{_esc(tech)}</span></div>')
        if target:
            rows.append(f'<div class="tech-row"><span class="tech-label">听完的状态</span><span class="tech-val">{_esc(target)}</span></div>')
        tech_badge_html = (
            '<aside class="tech-badge" aria-label="本期心理锚点">'
            + "".join(rows) +
            '</aside>'
        )

    # prev/next episode navigation (keeps listeners bingeing)
    nav_parts: list[str] = []
    if prev_ep:
        nav_parts.append(
            f'<a class="ep-nav-link ep-nav-prev" href="{_esc(_episode_slug(prev_ep))}.html">'
            f'<span class="ep-nav-dir">← 上一集</span>'
            f'<span class="ep-nav-title">{_esc(prev_ep["title"])}</span></a>'
        )
    else:
        nav_parts.append('<span class="ep-nav-link ep-nav-dummy"></span>')
    if next_ep:
        nav_parts.append(
            f'<a class="ep-nav-link ep-nav-next" href="{_esc(_episode_slug(next_ep))}.html">'
            f'<span class="ep-nav-dir">下一集 →</span>'
            f'<span class="ep-nav-title">{_esc(next_ep["title"])}</span></a>'
        )
    else:
        nav_parts.append('<span class="ep-nav-link ep-nav-dummy"></span>')
    nav_html = f'<nav class="ep-nav">{"".join(nav_parts)}</nav>'

    # related episodes (internal linking → SEO + dwell time)
    related_html = ""
    related = related or []
    if related:
        cards = []
        for r in related:
            r_desc_raw = (r.get("description") or r["draft_full"][:200]).strip()
            r_desc = _STRIP_RE.sub("", r_desc_raw)
            r_desc = re.sub(r"\s+", " ", r_desc).strip()[:80]
            cards.append(
                f'<a class="rel-card" href="{_esc(_episode_slug(r))}.html">'
                f'<div class="rel-theme">{_esc(r["theme"])}</div>'
                f'<div class="rel-title">{_esc(r["title"])}</div>'
                f'<div class="rel-desc">{_esc(r_desc)}</div></a>'
            )
        related_html = (
            '<section class="related"><h2>你可能还喜欢</h2>'
            f'<div class="rel-grid">{"".join(cards)}</div></section>'
        )

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(ep['title'])} | {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="{_esc(desc_plain[:160])}">
    <meta name="keywords" content="{_esc(keywords_meta)}">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{_esc(ep['title'])}">
    <meta property="og:description" content="{_esc(desc_plain[:160])}">
    <meta property="og:locale" content="zh_CN">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">
    {'<meta property="og:url" content="' + _esc(canonical) + '">' if site_url else ''}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{_esc(ep['title'])}">
    <meta name="twitter:description" content="{_esc(desc_plain[:160])}">
    <meta name="twitter:image" content="{_esc(og_image)}">
    <script type="application/ld+json">{json.dumps(jsonld_ep, ensure_ascii=False)}</script>
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.8;
    }}
    .wrap {{ max-width: 680px; margin: 0 auto; padding: 40px 20px 120px; }}
    .back {{
      display: inline-block; color: var(--dim); text-decoration: none;
      font-size: 0.85rem; margin-bottom: 20px; transition: color 0.2s;
    }}
    .back:hover {{ color: var(--accent); }}
    .theme-badge {{
      display: inline-block; font-size: 0.72rem; color: var(--accent);
      background: rgba(124,111,247,0.12); padding: 3px 12px; border-radius: 20px;
      margin-bottom: 12px;
    }}
    h1 {{
      font-size: 1.6rem; font-weight: 700; line-height: 1.4;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text; margin-bottom: 8px;
    }}
    .meta {{ font-size: 0.8rem; color: var(--dim); margin-bottom: 20px; }}
    .tags {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 24px; }}
    .tag {{
      font-size: 0.7rem; color: var(--dim);
      background: rgba(255,255,255,0.05); padding: 2px 8px; border-radius: 10px;
    }}
    .player {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 16px; padding: 18px; margin-bottom: 32px;
    }}
    .player audio {{ width: 100%; }}
    .share {{ display: flex; gap: 10px; margin-top: 12px; }}
    .share button {{
      background: none; border: 1px solid var(--border);
      color: var(--text); padding: 6px 14px; border-radius: 18px;
      cursor: pointer; font-size: 0.78rem; transition: all 0.2s;
    }}
    .share button:hover {{ border-color: var(--accent); color: var(--accent); }}
    .summary {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 14px 18px; margin-bottom: 32px;
      color: var(--dim); font-size: 0.88rem; line-height: 1.7;
    }}
    .tech-badge {{
      background: linear-gradient(135deg, rgba(124,111,247,0.06), rgba(240,194,127,0.03));
      border: 1px solid rgba(124,111,247,0.18);
      border-radius: 12px; padding: 14px 18px;
      margin-bottom: 20px;
      display: grid; gap: 8px;
    }}
    .tech-row {{ display: flex; gap: 12px; font-size: 0.82rem; line-height: 1.6; }}
    .tech-label {{
      color: var(--warm); font-weight: 500;
      min-width: 70px; flex-shrink: 0;
    }}
    .tech-val {{ color: var(--text); flex: 1; }}

    /* --- chapters (per-phase nav below player) --- */
    .chapters {{
      display: grid; gap: 6px;
      margin-bottom: 20px;
      grid-template-columns: 1fr;
    }}
    .chapter {{
      display: grid;
      grid-template-columns: 58px 1fr auto;
      gap: 14px; align-items: center;
      padding: 10px 14px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; cursor: pointer;
      color: var(--text); font-family: inherit; font-size: 0.86rem;
      text-align: left; transition: all 0.2s ease;
    }}
    .chapter:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
      transform: translateX(2px);
    }}
    .chapter.active {{
      background: rgba(124,111,247,0.1);
      border-color: var(--accent);
      color: var(--text);
    }}
    .chapter-time {{
      font-family: ui-monospace, "SF Mono", Menlo, monospace;
      color: var(--warm); font-size: 0.78rem;
    }}
    .chapter-name {{ font-weight: 500; }}
    .chapter-dur {{ color: var(--dim); font-size: 0.72rem; }}
    article.transcript {{ font-size: 0.95rem; }}
    article.transcript h2.phase {{
      font-size: 0.78rem; font-weight: 500; letter-spacing: 0.2em;
      color: var(--warm); margin: 40px 0 16px; text-transform: uppercase;
      border-left: 2px solid var(--warm); padding-left: 10px;
    }}
    article.transcript p {{
      margin-bottom: 16px; color: var(--text);
    }}
    article.transcript .cue {{
      color: var(--dim); font-style: italic; font-size: 0.88em;
    }}
    .footer-nav {{
      margin-top: 60px; padding-top: 24px;
      border-top: 1px solid var(--border);
      display: flex; justify-content: space-between;
      font-size: 0.8rem;
    }}
    .footer-nav a {{ color: var(--dim); text-decoration: none; }}
    .footer-nav a:hover {{ color: var(--accent); }}
    .ep-nav {{
      display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
      margin-top: 44px;
    }}
    .ep-nav-link {{
      display: flex; flex-direction: column; gap: 4px;
      padding: 14px 16px; border-radius: 12px;
      background: var(--card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease; min-height: 64px;
    }}
    .ep-nav-link:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
      transform: translateY(-1px);
    }}
    .ep-nav-next {{ text-align: right; }}
    .ep-nav-dir {{ font-size: 0.7rem; color: var(--dim); }}
    .ep-nav-title {{ font-size: 0.88rem; font-weight: 600; line-height: 1.4;
      overflow: hidden; text-overflow: ellipsis; display: -webkit-box;
      -webkit-line-clamp: 2; -webkit-box-orient: vertical; }}
    .ep-nav-dummy {{ visibility: hidden; }}
    .related {{
      margin-top: 48px; padding-top: 24px;
      border-top: 1px solid var(--border);
    }}
    .related h2 {{
      font-size: 0.88rem; color: var(--text); font-weight: 600;
      margin-bottom: 14px;
    }}
    .rel-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }}
    .rel-card {{
      display: block; padding: 14px; border-radius: 12px;
      background: var(--card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .rel-card:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
    }}
    .rel-theme {{
      font-size: 0.68rem; color: var(--accent);
      background: rgba(124,111,247,0.12); display: inline-block;
      padding: 2px 8px; border-radius: 10px; margin-bottom: 6px;
    }}
    .rel-title {{ font-size: 0.85rem; font-weight: 600; line-height: 1.4; margin-bottom: 4px; }}
    .rel-desc {{ font-size: 0.72rem; color: var(--dim); line-height: 1.5; }}
    .toast {{
      position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%);
      background: rgba(124,111,247,0.95); color: #fff;
      padding: 10px 20px; border-radius: 24px; font-size: 0.8rem;
      opacity: 0; transition: opacity 0.3s; pointer-events: none;
    }}
    .toast.show {{ opacity: 1; }}
    @media (max-width: 600px) {{
      .wrap {{ padding: 24px 16px 80px; }}
      h1 {{ font-size: 1.3rem; }}
    }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="../index.html">← 回到所有节目</a>
        {'<a class="theme-badge" href="../category/' + _esc(theme_cfg.get('category', '')) + '.html">' if theme_cfg.get('category') else '<span class="theme-badge">'}{_esc(ep['theme'])}{'</a>' if theme_cfg.get('category') else '</span>'}
        <h1>{_esc(ep['title'])}</h1>
        <div class="meta">{ep['timestamp'].strftime('%Y-%m-%d')} · {ep['word_count']} 字 · {_fmt_duration(ep['duration'])}</div>
        <div class="tags">{tags_html}</div>

        <div class="player">
          <audio controls preload="metadata" src="{_esc(audio_src)}"></audio>
          <div class="share">
            <button onclick="shareEp()">📤 分享</button>
            <button onclick="copyLink()">🔗 复制链接</button>
          </div>
        </div>

        {chapters_html}

        {tech_badge_html}

        {'<div class="summary">' + _esc(desc_plain) + '</div>' if desc_plain else ''}

        <article class="transcript">
          {transcript_html}
        </article>

        {nav_html}

        {related_html}

        <div class="footer-nav">
          <a href="../index.html">← 所有 {total_eps} 期</a>
          <a href="../about.html">关于</a>
          <a href="../feed.xml">RSS 订阅 →</a>
        </div>
      </div>

      <div class="toast" id="toast">已复制</div>
      <script>
      function shareEp() {{
        const url = location.href;
        const title = {json.dumps(share_text, ensure_ascii=False)};
        if (navigator.share) {{
          navigator.share({{ title, url }}).catch(() => {{}});
        }} else {{
          copyLink();
        }}
      }}
      function copyLink() {{
        navigator.clipboard.writeText(location.href).then(() => {{
          const t = document.getElementById('toast');
          t.classList.add('show');
          setTimeout(() => t.classList.remove('show'), 1400);
        }});
      }}

      // --- Chapter navigation ---
      (function() {{
        const audioEl = document.querySelector('.player audio');
        const chapters = document.querySelectorAll('.chapter');
        if (!audioEl || !chapters.length) return;
        chapters.forEach(btn => {{
          btn.addEventListener('click', () => {{
            const t = parseFloat(btn.dataset.start);
            if (!isNaN(t)) {{
              audioEl.currentTime = t;
              audioEl.play().catch(() => {{}});
            }}
          }});
        }});
        // Highlight the current chapter as playback progresses
        const starts = Array.from(chapters).map(c => parseFloat(c.dataset.start));
        audioEl.addEventListener('timeupdate', () => {{
          const t = audioEl.currentTime;
          let activeIdx = -1;
          for (let i = 0; i < starts.length; i++) {{
            if (t >= starts[i]) activeIdx = i;
          }}
          chapters.forEach((c, i) => c.classList.toggle('active', i === activeIdx));
        }});
      }})();
      </script>
    </body>
    </html>
    """)


def generate_category_page(cat_key: str, cat_cfg: dict, episodes: list[dict],
                            monetization: dict, base_url: str) -> str:
    """Landing page for a single category — targets the category's SEO keywords
    and lists all episodes that belong to it. One more indexed page per category,
    focused intent matching (e.g. zeitgeist_2026 page targets '裁员 焦虑' etc.)."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    label = cat_cfg.get("label", cat_key)
    desc = cat_cfg.get("description", "")
    seo_keywords = cat_cfg.get("seo_keywords", [])
    canonical = f"{site_url}/category/{cat_key}.html" if site_url else f"category/{cat_key}.html"
    og_image = f"{site_url}/og/home.png" if site_url else "../og/home.png"
    analytics_head = _build_analytics_head(m)

    cards: list[str] = []
    for ep in episodes:
        theme_cfg = _THEMES.get(ep["theme"]) or {}
        if theme_cfg.get("category") != cat_key:
            continue
        tags_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in ep["tags"][:3])
        desc_short = ep["description"][:90] + "…" if len(ep["description"]) > 90 else ep["description"]
        pain = theme_cfg.get("pain_point", "").strip()
        pain_html = f'<div class="card-pain">痛点：{_esc(pain)}</div>' if pain else ""
        cards.append(f"""
        <a class="ep-card" href="../episodes/{_esc(_episode_slug(ep))}.html">
          <div class="ep-head">
            <span class="ep-theme">{_esc(ep['theme'])}</span>
            <span class="ep-meta">{_fmt_duration(ep['duration'])}</span>
          </div>
          <h3 class="ep-title">{_esc(ep['title'])}</h3>
          {pain_html}
          <p class="ep-desc">{_esc(desc_short)}</p>
          <div class="ep-tags">{tags_html}</div>
        </a>""")

    if not cards:
        cards.append('<p class="empty-note">此分类暂无节目——新内容将在下次生产后出现。</p>')

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(label)} · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="{_esc(desc[:160])}">
    <meta name="keywords" content="{_esc(','.join(seo_keywords + ['助眠', '睡眠', '冥想']))}">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="website">
    <meta property="og:title" content="{_esc(label)} · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="{_esc(desc[:160])}">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.75;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    header {{ margin: 24px 0 36px; }}
    h1 {{
      font-size: 1.6rem; margin-bottom: 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .cat-desc {{ color: var(--dim); font-size: 0.95rem; }}
    .ep-card {{
      display: block; padding: 18px 20px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 14px; margin-bottom: 12px;
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .ep-card:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
      transform: translateY(-1px);
    }}
    .ep-head {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
    .ep-theme {{
      font-size: 0.72rem; color: var(--accent);
      background: rgba(124,111,247,0.12);
      padding: 2px 10px; border-radius: 12px;
    }}
    .ep-meta {{ font-size: 0.72rem; color: var(--dim); }}
    .ep-title {{ font-size: 1rem; font-weight: 600; line-height: 1.5; margin-bottom: 6px; }}
    .card-pain {{
      font-size: 0.78rem; color: var(--warm);
      margin-bottom: 6px; line-height: 1.5;
    }}
    .ep-desc {{ font-size: 0.85rem; color: var(--dim); margin-bottom: 8px; line-height: 1.65; }}
    .ep-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .tag {{
      font-size: 0.7rem; color: var(--dim);
      background: rgba(255,255,255,0.05);
      padding: 2px 8px; border-radius: 10px;
    }}
    .empty-note {{
      color: var(--dim); text-align: center; padding: 40px 20px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px;
    }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; justify-content: space-between;
      font-size: 0.82rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="../index.html">← 回到首页</a>
        <header>
          <h1>{_esc(label)}</h1>
          <p class="cat-desc">{_esc(desc)}</p>
        </header>
        <main>
          {''.join(cards)}
        </main>
        <div class="footer">
          <a href="../index.html">全部节目</a>
          <a href="../about.html">关于</a>
          <a href="../feed.xml">RSS</a>
        </div>
      </div>
    </body>
    </html>
    """)


def generate_about_page(monetization: dict, base_url: str) -> str:
    """Generate site/about.html — trust-building page explaining what the site is,
    the 4 theme categories, how episodes are produced, and transparent monetization.

    Critical for an AI-generated content site: skeptical visitors need to see the
    process before they subscribe / donate / click affiliate links."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/about.html" if site_url else "about.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    # Category sections: pull from THEME_CATEGORIES + count themes per category
    cat_sections: list[str] = []
    by_cat: dict[str, list[str]] = {}
    for name, cfg in (_THEMES or {}).items():
        by_cat.setdefault(cfg.get("category", "其他"), []).append(name)
    for cat_key, cat_cfg in (_THEME_CATEGORIES or {}).items():
        names = by_cat.get(cat_key, [])
        if not names:
            continue
        label = cat_cfg.get("label", cat_key)
        desc = cat_cfg.get("description", "")
        theme_list = "、".join(names)
        cat_sections.append(f"""
        <section class="cat">
          <h3>{_esc(label)} · {len(names)} 期</h3>
          <p class="cat-desc">{_esc(desc)}</p>
          <p class="cat-themes">{_esc(theme_list)}</p>
        </section>""")

    # Monetization transparency block
    reveal_parts = []
    don = m.get("donation") or {}
    if don.get("enabled"):
        reveal_parts.append(f"<li>打赏（{_esc(don.get('label', '自愿'))}）— 一次性小额资助电台运营</li>")
    spon = m.get("sponsor_slot") or {}
    if spon.get("enabled"):
        reveal_parts.append("<li>品牌赞助 — 每期开头/结尾可能出现的品牌提及，会明确标注「赞助」字样</li>")
    aff = m.get("affiliates") or {}
    if aff.get("enabled"):
        reveal_parts.append("<li>联盟推荐 — 助眠相关商品（眼罩/白噪音机/耳塞等），通过链接购买你不会多花钱但电台会拿到一点分成</li>")
    prem = m.get("premium") or {}
    if prem.get("enabled"):
        reveal_parts.append("<li>会员内容 — 部分长版/无 BGM 纯人声版将对付费会员开放</li>")
    reveal_html = ""
    if reveal_parts:
        reveal_html = f"""
        <section class="trust">
          <h2>透明变现披露</h2>
          <p>我们相信助眠内容的本质是信任——所以你有权知道我们怎么挣钱：</p>
          <ul>{''.join(reveal_parts)}</ul>
          <p class="trust-note">所有变现位都不会影响内容本身的心理学质量。联盟商品是我们自己也会用的。</p>
        </section>"""

    contact_email = ((m.get("social") or {}).get("contact_email") or "").strip()
    contact_html = ""
    if contact_email:
        contact_html = f'<p class="contact">有建议或合作意向？<a href="mailto:{_esc(contact_email)}">{_esc(contact_email)}</a></p>'

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>关于 · {PODCAST_TITLE}</title>
    <meta name="description" content="助眠电台的设计理念、18 个主题 4 大分类的心理学基础、AI 生成流程透明披露、变现模式披露。">
    <meta name="keywords" content="助眠电台,关于,心理学,ACT,安全岛,韵律弧线,AI生成,催眠,冥想">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="关于 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="4 大分类 18 个主题的心理学基础 + 生产流程透明披露">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {analytics_head}
    <style>
    :root {{
      --bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a;
      --accent: #7c6ff7; --warm: #f0c27f;
      --card: rgba(255,255,255,0.04); --border: rgba(255,255,255,0.08);
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", sans-serif;
      background: var(--bg); color: var(--text);
      min-height: 100vh; line-height: 1.85;
    }}
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 60px 20px 100px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 2rem; margin: 16px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 1.02rem; margin-bottom: 40px; }}
    h2 {{
      font-size: 1.15rem; font-weight: 600;
      margin: 40px 0 14px; color: var(--text);
      border-left: 3px solid var(--accent); padding-left: 12px;
    }}
    h3 {{ font-size: 1rem; font-weight: 600; margin: 20px 0 8px; color: var(--warm); }}
    p {{ color: var(--text); margin-bottom: 14px; font-size: 0.95rem; }}
    ul {{ padding-left: 20px; margin-bottom: 16px; }}
    li {{ color: var(--text); margin-bottom: 8px; font-size: 0.92rem; }}
    .cat {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 16px 20px; margin-bottom: 14px;
    }}
    .cat-desc {{ font-size: 0.88rem; color: var(--dim); margin-bottom: 8px; }}
    .cat-themes {{ font-size: 0.82rem; color: var(--warm); margin: 0; }}
    .process {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 20px; margin-top: 10px;
    }}
    .process ol {{ counter-reset: step; padding-left: 0; list-style: none; }}
    .process li {{
      position: relative; padding-left: 36px; counter-increment: step;
    }}
    .process li::before {{
      content: counter(step);
      position: absolute; left: 0; top: 0;
      width: 24px; height: 24px; border-radius: 50%;
      background: rgba(124,111,247,0.18); color: var(--accent);
      display: flex; align-items: center; justify-content: center;
      font-size: 0.75rem; font-weight: 600;
    }}
    .trust {{
      background: linear-gradient(135deg, rgba(240,194,127,0.06), rgba(124,111,247,0.04));
      border: 1px solid rgba(240,194,127,0.2);
      border-radius: 12px; padding: 20px 24px;
    }}
    .trust-note {{ color: var(--dim); font-size: 0.85rem; margin-top: 10px; }}
    .contact {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border); color: var(--dim);
    }}
    .contact a {{ color: var(--accent); }}
    code {{
      background: rgba(255,255,255,0.06); padding: 1px 7px;
      border-radius: 5px; font-family: ui-monospace, Menlo, monospace;
      color: var(--warm); font-size: 0.88em;
    }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>关于助眠电台</h1>
        <p class="lede">用 AI 写稿、真人级韵律合成、心理学技术引导——每晚 10 分钟，把脑子里的白天声音关小。</p>

        <h2>这是什么</h2>
        <p>一个按主题批量生产的助眠音频电台。每一期由三轮 LLM 写稿（大纲 → 扩写 → 润色）+ 质量评分 + 低分自动重写组成；语音用韵律弧线引擎控制语速、音量、停顿从正常逐渐降到接近呢喃的状态；再叠上匹配的 BGM 和可选的双耳节拍。</p>

        <h2>4 大主题分类</h2>
        <p>18 个主题按「这对谁有用」分 4 类。每个主题都有明确的<strong>痛点 / 心理或感官技术 / 目标状态</strong>三要素——不是随便想一个场景。</p>
        {''.join(cat_sections)}

        <h2>韵律弧线引擎</h2>
        <p>普通 TTS 全篇匀速。我们用 Prosody Curve 分三段控制节奏：</p>
        <ul>
          <li><strong>引入段（前 30%）</strong>：<code>speed=1.0, vol=1.0, pause=0.3s</code> — 自然语速承认感受</li>
          <li><strong>深入段（30-70%）</strong>：<code>speed=0.82, vol=0.85, pause=0.6s</code> — 引导放松</li>
          <li><strong>尾声段（后 30%）</strong>：<code>speed=0.55, vol=0.3, pause=2.0s</code> — 接近呢喃、带入睡眠</li>
        </ul>
        <p>内联标记 <code>[慢速]</code>/<code>[轻声]</code>/<code>[极弱]</code> 是乘法叠加在曲线上——同一个标记越靠近尾声效果越强。</p>

        <h2>AI 生成流程透明披露</h2>
        <p>每期剧本的质量闭环：</p>
        <div class="process">
          <ol>
            <li><strong>大纲生成</strong>：把主题的 pain_point / technique / emotional_target 注入 prompt，LLM 输出三段式心理暗示大纲</li>
            <li><strong>扩写成稿</strong>：按目标字数扩写，必须具体承认痛点画面（禁止笼统「今天辛苦了」）</li>
            <li><strong>主编润色</strong>：去 AI 腔、禁用排比/反问/说教/集体措辞，保留所有韵律标记</li>
            <li><strong>质量评估</strong>：5 维各 20 分（催眠感 / 感官描写 / 节奏标记 / 去 AI 腔 / 痛点对齐）</li>
            <li><strong>低分重写</strong>：评分 &lt;70 自动按评审反馈重写一次，再次评分</li>
          </ol>
        </div>
        {reveal_html}

        <h2>技术栈</h2>
        <p>开源自治——<a href="https://github.com/beerui/bedtime_story_agent" target="_blank" rel="noopener" style="color:var(--accent)">GitHub 源码</a>。文本用 Qwen（通义千问），语音用 CosyVoice（配额耗尽自动降级 edge-tts），封面用 Pillow 生成，站点是纯 HTML/CSS/JS 无任何框架。</p>

        {contact_html}
      </div>
    </body>
    </html>
    """)


def generate_sitemap(episodes: list[dict], base_url: str) -> str:
    """XML sitemap listing all pages — helps Google/Bing index the long-tail."""
    base = (base_url or "").rstrip("/")
    urls: list[str] = []
    homepage = f"{base}/" if base else "./"
    urls.append(f"""  <url>
    <loc>{homepage}</loc>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>""")
    for ep in episodes:
        loc = f"{base}/episodes/{_episode_slug(ep)}.html" if base else f"episodes/{_episode_slug(ep)}.html"
        lastmod = ep["timestamp"].strftime("%Y-%m-%d")
        urls.append(f"""  <url>
    <loc>{loc}</loc>
    <lastmod>{lastmod}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.8</priority>
  </url>""")
    # category landing pages — only include categories that actually have episodes
    cat_keys_used: set[str] = set()
    for ep in episodes:
        k = (_THEMES.get(ep["theme"]) or {}).get("category")
        if k:
            cat_keys_used.add(k)
    for ck in cat_keys_used:
        cloc = f"{base}/category/{ck}.html" if base else f"category/{ck}.html"
        urls.append(f"""  <url>
    <loc>{cloc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.7</priority>
  </url>""")
    about_loc = f"{base}/about.html" if base else "about.html"
    urls.append(f"""  <url>
    <loc>{about_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    body = "\n".join(urls)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{body}
</urlset>
"""


def generate_robots(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    sitemap_url = f"{base}/sitemap.xml" if base else "sitemap.xml"
    return f"""User-agent: *
Allow: /

Sitemap: {sitemap_url}
"""


def generate_html(episodes: list[dict], monetization: dict | None = None, base_url: str = "") -> str:
    """Generate a self-contained dark-themed HTML player page."""
    monetization = monetization or {}

    episode_cards = []
    for i, ep in enumerate(episodes):
        tags_html = "".join(f'<span class="tag">{t}</span>' for t in ep["tags"][:4])
        desc_short = ep["description"][:120] + "…" if len(ep["description"]) > 120 else ep["description"]
        srt_attr = f' data-srt="{ep["srt"][:3000]}"' if ep["srt"] else ""
        audio_src = resolve_html_audio(ep)
        ep_href = _episode_href(ep)
        cat_attr = (_THEMES.get(ep["theme"]) or {}).get("category", "")

        episode_cards.append(f"""
      <article class="episode" data-audio="{audio_src}" data-cat="{cat_attr}"{srt_attr}>
        <div class="ep-header">
          <span class="ep-theme">{ep['theme']}</span>
          <span class="ep-meta">{ep['word_count']} 字 · {_fmt_duration(ep['duration'])}</span>
        </div>
        <h3 class="ep-title">{ep['title']}</h3>
        <p class="ep-desc">{desc_short}</p>
        <div class="ep-tags">{tags_html}</div>
        <a class="ep-read" href="{ep_href}">阅读全文 →</a>
        <button class="play-btn" onclick="togglePlay(this, {i})">
          <svg class="icon-play" viewBox="0 0 24 24"><polygon points="5,3 19,12 5,21"/></svg>
          <svg class="icon-pause" viewBox="0 0 24 24" style="display:none"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
        </button>
      </article>""")

    cards_html = "\n".join(episode_cards)
    total_eps = len(episodes)
    total_dur = sum(e["duration"] for e in episodes)
    support_html = _build_support_html(monetization)
    head_meta = _build_head_meta(episodes, monetization, base_url)
    site_url = (base_url or (monetization or {}).get("site_url") or "").rstrip("/")
    absolute_feed = f"{site_url}/feed.xml" if site_url else "feed.xml"
    subscribe_html = _build_subscribe_html(monetization or {}, absolute_feed)

    # Category filter chips — only render when a category has at least 1 episode
    cat_counts: dict[str, int] = {}
    for ep in episodes:
        key = (_THEMES.get(ep["theme"]) or {}).get("category") or ""
        if key:
            cat_counts[key] = cat_counts.get(key, 0) + 1
    filter_chips_html = ""
    if cat_counts and _THEME_CATEGORIES:
        chips = [f'<button class="chip chip-all active" data-cat="">全部 <span class="chip-num">{total_eps}</span></button>']
        for cat_key, cat_cfg in _THEME_CATEGORIES.items():
            n = cat_counts.get(cat_key, 0)
            if n == 0:
                continue
            label = cat_cfg.get("label", cat_key)
            chips.append(
                f'<button class="chip" data-cat="{_esc(cat_key)}" data-track="Filter Category" '
                f'data-prop-cat="{_esc(cat_key)}">'
                f'{_esc(label)} <a class="chip-deep" href="category/{_esc(cat_key)}.html" '
                f'onclick="event.stopPropagation()">→</a> '
                f'<span class="chip-num">{n}</span></button>'
            )
        filter_chips_html = f'<nav class="filter-chips" role="tablist">{"".join(chips)}</nav>'

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>助眠电台</title>
    {head_meta}
    <style>
    :root {{
      --bg-deep: #06061a;
      --bg-card: rgba(255,255,255,0.04);
      --bg-card-hover: rgba(255,255,255,0.07);
      --border: rgba(255,255,255,0.08);
      --text: #d4d4e0;
      --text-dim: #7a7a9a;
      --accent: #7c6ff7;
      --accent-glow: rgba(124,111,247,0.3);
      --warm: #f0c27f;
    }}
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    body {{
      font-family: -apple-system, "PingFang SC", "Noto Sans SC", "Microsoft YaHei", sans-serif;
      background: var(--bg-deep);
      color: var(--text);
      min-height: 100vh;
      overflow-x: hidden;
      transition: opacity 2s ease;
    }}
    body.dimmed {{ opacity: 0.3; }}

    /* --- starfield --- */
    .stars {{
      position: fixed; inset: 0; z-index: 0; overflow: hidden; pointer-events: none;
    }}
    .stars span {{
      position: absolute; border-radius: 50%; background: #fff;
      animation: twinkle var(--dur) ease-in-out infinite alternate;
    }}
    @keyframes twinkle {{ 0% {{ opacity: 0.1; }} 100% {{ opacity: var(--peak); }} }}

    /* --- layout --- */
    .container {{
      position: relative; z-index: 1;
      max-width: 680px; margin: 0 auto; padding: 60px 20px 120px;
    }}
    header {{ text-align: center; margin-bottom: 48px; }}
    header h1 {{
      font-size: 1.8rem; font-weight: 700;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    header p {{ color: var(--text-dim); margin-top: 8px; font-size: 0.9rem; }}
    .stats {{
      display: flex; justify-content: center; gap: 24px; margin-top: 16px;
      font-size: 0.8rem; color: var(--text-dim);
      flex-wrap: wrap;
    }}
    .stats b {{ color: var(--warm); font-weight: 600; }}
    .stats-link {{ color: var(--text-dim); text-decoration: none; transition: color 0.2s; }}
    .stats-link:hover {{ color: var(--accent); }}

    /* --- episode card --- */
    .episode {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 16px; padding: 24px; margin-bottom: 16px;
      position: relative; transition: all 0.3s ease;
      cursor: default;
    }}
    .episode:hover {{ background: var(--bg-card-hover); border-color: rgba(124,111,247,0.2); }}
    .episode.active {{ border-color: var(--accent); box-shadow: 0 0 24px var(--accent-glow); }}
    .ep-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }}
    .ep-theme {{
      font-size: 0.75rem; color: var(--accent); background: rgba(124,111,247,0.12);
      padding: 2px 10px; border-radius: 20px;
    }}
    .ep-meta {{ font-size: 0.75rem; color: var(--text-dim); }}
    .ep-title {{ font-size: 1.05rem; font-weight: 600; line-height: 1.5; margin-bottom: 6px; }}
    .ep-desc {{ font-size: 0.85rem; color: var(--text-dim); line-height: 1.6; margin-bottom: 10px; }}
    .ep-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .tag {{
      font-size: 0.7rem; color: var(--text-dim); background: rgba(255,255,255,0.05);
      padding: 2px 8px; border-radius: 10px;
    }}
    .ep-read {{
      display: inline-block; font-size: 0.72rem; color: var(--accent);
      text-decoration: none; margin-top: 10px; opacity: 0.75;
      transition: opacity 0.2s;
    }}
    .ep-read:hover {{ opacity: 1; }}
    .play-btn {{
      position: absolute; right: 24px; top: 50%; transform: translateY(-50%);
      width: 48px; height: 48px; border-radius: 50%;
      background: linear-gradient(135deg, var(--accent), #9b6ff7);
      border: none; cursor: pointer; display: flex; align-items: center; justify-content: center;
      transition: all 0.3s ease; box-shadow: 0 4px 16px var(--accent-glow);
    }}
    .play-btn:hover {{ transform: translateY(-50%) scale(1.08); }}
    .play-btn svg {{ width: 20px; height: 20px; fill: #fff; }}
    .icon-play {{ margin-left: 2px; }}

    /* --- bottom player bar --- */
    .player-bar {{
      position: fixed; bottom: 0; left: 0; right: 0; z-index: 10;
      background: rgba(10,10,30,0.95); backdrop-filter: blur(20px);
      border-top: 1px solid var(--border);
      padding: 0; transform: translateY(100%); transition: transform 0.4s ease;
    }}
    .player-bar.show {{ transform: translateY(0); }}
    .progress-wrap {{
      height: 4px; background: rgba(255,255,255,0.06); cursor: pointer; position: relative;
    }}
    .progress-wrap:hover {{ height: 6px; }}
    .progress-fill {{
      height: 100%; background: linear-gradient(90deg, var(--accent), var(--warm));
      width: 0%; transition: width 0.2s linear; border-radius: 0 2px 2px 0;
    }}
    .player-inner {{
      display: flex; align-items: center; padding: 12px 20px; gap: 16px;
      max-width: 680px; margin: 0 auto;
    }}
    .player-info {{ flex: 1; min-width: 0; }}
    .player-title {{ font-size: 0.85rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
    .player-time {{ font-size: 0.7rem; color: var(--text-dim); margin-top: 2px; }}
    .player-subtitle {{
      font-size: 0.8rem; color: var(--warm); margin-top: 4px;
      min-height: 1.2em; transition: opacity 0.5s ease;
    }}
    .player-controls {{ display: flex; align-items: center; gap: 12px; }}
    .ctrl-btn {{
      background: none; border: none; cursor: pointer; color: var(--text); padding: 4px;
      opacity: 0.7; transition: opacity 0.2s;
    }}
    .ctrl-btn:hover {{ opacity: 1; }}
    .ctrl-btn svg {{ width: 18px; height: 18px; fill: currentColor; }}

    /* sleep timer dropdown */
    .timer-wrap {{ position: relative; }}
    .timer-menu {{
      position: absolute; bottom: 100%; right: 0; margin-bottom: 8px;
      background: rgba(20,20,50,0.97); border: 1px solid var(--border);
      border-radius: 12px; padding: 8px 0; display: none; min-width: 130px;
    }}
    .timer-menu.show {{ display: block; }}
    .timer-opt {{
      display: block; width: 100%; text-align: left; padding: 8px 16px;
      background: none; border: none; color: var(--text); font-size: 0.8rem;
      cursor: pointer;
    }}
    .timer-opt:hover {{ background: rgba(255,255,255,0.06); }}
    .timer-opt.active {{ color: var(--warm); }}
    .timer-badge {{
      font-size: 0.6rem; color: var(--warm); background: rgba(240,194,127,0.15);
      padding: 1px 6px; border-radius: 8px; margin-left: 4px;
    }}

    @media (max-width: 600px) {{
      .container {{ padding: 40px 16px 140px; }}
      .episode {{ padding: 18px; padding-right: 70px; }}
      .play-btn {{ width: 40px; height: 40px; right: 16px; }}
      header h1 {{ font-size: 1.4rem; }}
    }}

    /* --- subscribe row (primary CTA, above the fold) --- */
    .subscribe {{
      margin: 0 0 36px;
      padding: 20px 22px;
      background: linear-gradient(135deg, rgba(124,111,247,0.08), rgba(240,194,127,0.05));
      border: 1px solid rgba(124,111,247,0.15);
      border-radius: 16px;
    }}
    .sub-title {{
      font-size: 0.78rem; color: var(--warm);
      letter-spacing: 0.15em; text-transform: uppercase;
      margin-bottom: 12px;
    }}
    .sub-row {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .sub-btn {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 8px 14px; border-radius: 22px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      font-size: 0.78rem; font-family: inherit;
      cursor: pointer; transition: all 0.25s ease;
    }}
    .sub-btn:hover {{
      background: rgba(255,255,255,0.08);
      border-color: rgba(124,111,247,0.4);
      color: var(--accent);
      transform: translateY(-1px);
    }}
    .sub-btn.copied {{
      border-color: var(--warm);
      color: var(--warm);
    }}
    .sub-logo {{ font-size: 1rem; line-height: 1; }}
    .sub-hint {{
      font-size: 0.7rem; color: var(--text-dim);
      margin-top: 10px; line-height: 1.5;
    }}

    /* --- category filter chips --- */
    .filter-chips {{
      display: flex; flex-wrap: wrap; gap: 8px;
      margin-bottom: 24px;
    }}
    .chip {{
      display: inline-flex; align-items: center; gap: 6px;
      padding: 7px 14px; border-radius: 18px;
      background: var(--bg-card); border: 1px solid var(--border);
      color: var(--text-dim); font-size: 0.8rem; font-family: inherit;
      cursor: pointer; transition: all 0.2s ease;
    }}
    .chip:hover {{ border-color: rgba(124,111,247,0.3); color: var(--text); }}
    .chip.active {{
      background: rgba(124,111,247,0.15); color: var(--accent);
      border-color: rgba(124,111,247,0.4);
    }}
    .chip-num {{
      font-size: 0.68rem; opacity: 0.7;
      background: rgba(255,255,255,0.05);
      padding: 1px 6px; border-radius: 10px; min-width: 22px; text-align: center;
    }}
    .chip-deep {{
      color: inherit; text-decoration: none;
      font-size: 0.85rem; opacity: 0.55;
      margin-left: -2px;
    }}
    .chip-deep:hover {{ opacity: 1; }}
    .episode.hide-by-filter {{ display: none; }}

    /* --- support / monetization --- */
    .support, .affiliates {{
      margin-top: 48px;
      padding-top: 32px;
      border-top: 1px solid var(--border);
    }}
    .support h2, .affiliates h2 {{
      font-size: 0.95rem;
      color: var(--text);
      font-weight: 600;
      margin-bottom: 16px;
      letter-spacing: 0.02em;
    }}
    .support-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }}
    .support-tile {{
      display: flex; align-items: center; gap: 12px;
      padding: 14px 16px; border-radius: 12px;
      background: var(--bg-card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .support-tile:hover {{
      background: var(--bg-card-hover);
      border-color: rgba(124,111,247,0.28);
      transform: translateY(-1px);
    }}
    .support-donation {{ border-color: rgba(240,194,127,0.25); }}
    .support-donation:hover {{ box-shadow: 0 4px 18px rgba(240,194,127,0.15); }}
    .support-premium {{ border-color: rgba(124,111,247,0.3); }}
    .support-icon {{ font-size: 1.6rem; line-height: 1; }}
    .support-body {{ flex: 1; min-width: 0; }}
    .support-title {{ font-size: 0.88rem; font-weight: 600; margin-bottom: 2px; }}
    .support-note {{ font-size: 0.72rem; color: var(--text-dim); line-height: 1.5; }}

    .aff-disclaimer {{
      font-size: 0.7rem; color: var(--text-dim);
      margin-top: -8px; margin-bottom: 14px; line-height: 1.6;
    }}
    .aff-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }}
    .aff-card {{
      display: block; padding: 14px;
      border-radius: 12px; background: var(--bg-card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .aff-card:hover {{
      background: var(--bg-card-hover);
      border-color: rgba(124,111,247,0.28);
    }}
    .aff-emoji {{ font-size: 1.4rem; margin-bottom: 6px; }}
    .aff-title {{ font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; }}
    .aff-desc {{ font-size: 0.7rem; color: var(--text-dim); line-height: 1.5; }}
    </style>
    </head>
    <body>

    <div class="stars" id="stars"></div>

    <div class="container">
      <header>
        <h1>助眠电台</h1>
        <p>AI 生成 · 韵律弧线催眠 · 每期独一无二</p>
        <div class="stats">
          <span><b>{total_eps}</b> 期节目</span>
          <span><b>{_fmt_duration(total_dur)}</b> 总时长</span>
          <a class="stats-link" href="about.html">关于 →</a>
        </div>
      </header>

      {subscribe_html}

      {filter_chips_html}

      <main id="episodes">
        {cards_html}
      </main>
      {support_html}
    </div>

    <!-- bottom player -->
    <div class="player-bar" id="playerBar">
      <div class="progress-wrap" id="progressWrap" onclick="seek(event)">
        <div class="progress-fill" id="progressFill"></div>
      </div>
      <div class="player-inner">
        <div class="player-info">
          <div class="player-title" id="playerTitle">—</div>
          <div class="player-time"><span id="curTime">0:00</span> / <span id="totalTime">0:00</span></div>
          <div class="player-subtitle" id="playerSub"></div>
        </div>
        <div class="player-controls">
          <div class="timer-wrap">
            <button class="ctrl-btn" onclick="toggleTimerMenu()" title="睡眠定时">
              <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/><polyline points="12,7 12,12 16,14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
              <span class="timer-badge" id="timerBadge" style="display:none"></span>
            </button>
            <div class="timer-menu" id="timerMenu">
              <button class="timer-opt" onclick="setSleepTimer(0)">关闭</button>
              <button class="timer-opt" onclick="setSleepTimer(15)">15 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(30)">30 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(45)">45 分钟</button>
              <button class="timer-opt" onclick="setSleepTimer(60)">60 分钟</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <audio id="audio" preload="metadata"></audio>

    <script>
    // --- Analytics event helper (tries Plausible → Umami → GA4) ---
    function trackEvent(name, props) {{
      try {{
        if (window.plausible) {{ window.plausible(name, props ? {{ props }} : undefined); return; }}
        if (window.umami) {{ window.umami.track(name, props || {{}}); return; }}
        if (window.gtag) {{ window.gtag('event', name, props || {{}}); return; }}
      }} catch (e) {{ /* don't block UI on analytics failures */ }}
    }}

    // Auto-track all [data-track] link clicks
    document.addEventListener('click', function(e) {{
      const el = e.target.closest('[data-track]');
      if (!el) return;
      const props = {{}};
      for (const attr of el.attributes) {{
        if (attr.name.startsWith('data-prop-')) {{
          props[attr.name.slice('data-prop-'.length)] = attr.value;
        }}
      }}
      trackEvent(el.dataset.track, Object.keys(props).length ? props : null);
    }});

    // --- Copy RSS feed to clipboard ---
    function copyFeed(btn, url) {{
      trackEvent('Copy RSS');
      navigator.clipboard.writeText(url).then(() => {{
        const label = btn.querySelector('.sub-label');
        const original = label.textContent;
        label.textContent = '已复制';
        btn.classList.add('copied');
        setTimeout(() => {{
          label.textContent = original;
          btn.classList.remove('copied');
        }}, 1600);
      }}).catch(() => {{ alert('请手动复制: ' + url); }});
    }}

    // --- Category filter chips ---
    (function() {{
      const chips = document.querySelectorAll('.filter-chips .chip');
      const eps = document.querySelectorAll('.episode');
      if (!chips.length || !eps.length) return;
      chips.forEach(chip => {{
        chip.addEventListener('click', (e) => {{
          // the inner <a class="chip-deep"> has stopPropagation; clicks here mean chip body
          if (e.target.closest('.chip-deep')) return;
          const cat = chip.dataset.cat;
          chips.forEach(c => c.classList.toggle('active', c === chip));
          eps.forEach(ep => {{
            const match = !cat || ep.dataset.cat === cat;
            ep.classList.toggle('hide-by-filter', !match);
          }});
        }});
      }});
    }})();

    // --- Starfield ---
    (function() {{
      const c = document.getElementById('stars');
      for (let i = 0; i < 80; i++) {{
        const s = document.createElement('span');
        const size = Math.random() * 2 + 1;
        s.style.cssText = `left:${{Math.random()*100}}%;top:${{Math.random()*100}}%;width:${{size}}px;height:${{size}}px;--dur:${{2+Math.random()*4}}s;--peak:${{0.3+Math.random()*0.7}}`;
        c.appendChild(s);
      }}
    }})();

    // --- Audio state ---
    const audio = document.getElementById('audio');
    const episodes = document.querySelectorAll('.episode');
    let currentIdx = -1;
    let srtCues = [];
    let sleepTimerId = null;
    let sleepRemaining = 0;

    function fmtTime(s) {{
      s = Math.floor(s);
      const m = Math.floor(s / 60);
      return m + ':' + String(s % 60).padStart(2, '0');
    }}

    function togglePlay(btn, idx) {{
      if (currentIdx === idx && !audio.paused) {{
        audio.pause();
        trackEvent('Pause Episode', {{ title: episodes[idx].querySelector('.ep-title').textContent }});
        showPauseState(idx, false);
        return;
      }}
      if (currentIdx !== idx) {{
        // load new episode
        const ep = episodes[idx];
        audio.src = ep.dataset.audio;
        document.getElementById('playerTitle').textContent = ep.querySelector('.ep-title').textContent;
        document.getElementById('playerBar').classList.add('show');
        srtCues = parseSRT(ep.dataset.srt || '');
        // deactivate previous
        if (currentIdx >= 0) {{
          episodes[currentIdx].classList.remove('active');
          showPauseState(currentIdx, false);
        }}
        ep.classList.add('active');
        currentIdx = idx;
        trackEvent('Play Episode', {{
          title: ep.querySelector('.ep-title').textContent,
          theme: ep.querySelector('.ep-theme').textContent,
        }});
      }} else {{
        trackEvent('Resume Episode', {{ title: episodes[idx].querySelector('.ep-title').textContent }});
      }}
      audio.play();
      showPauseState(idx, true);
    }}

    function showPauseState(idx, playing) {{
      const btn = episodes[idx].querySelector('.play-btn');
      btn.querySelector('.icon-play').style.display = playing ? 'none' : 'block';
      btn.querySelector('.icon-pause').style.display = playing ? 'block' : 'none';
    }}

    // --- Progress ---
    let completionFired = false;
    audio.addEventListener('timeupdate', () => {{
      if (!audio.duration) return;
      const pct = (audio.currentTime / audio.duration) * 100;
      document.getElementById('progressFill').style.width = pct + '%';
      document.getElementById('curTime').textContent = fmtTime(audio.currentTime);
      document.getElementById('totalTime').textContent = fmtTime(audio.duration);
      // subtitle
      const sub = document.getElementById('playerSub');
      const cue = srtCues.find(c => audio.currentTime >= c.start && audio.currentTime <= c.end);
      sub.textContent = cue ? cue.text : '';
      // fire completion event at 80% (podcast industry standard for "listened")
      if (!completionFired && pct >= 80 && currentIdx >= 0) {{
        completionFired = true;
        trackEvent('Complete Episode', {{
          title: episodes[currentIdx].querySelector('.ep-title').textContent,
          theme: episodes[currentIdx].querySelector('.ep-theme').textContent,
        }});
      }}
    }});

    audio.addEventListener('loadstart', () => {{ completionFired = false; }});

    audio.addEventListener('ended', () => {{
      showPauseState(currentIdx, false);
      // auto-play next
      if (currentIdx < episodes.length - 1) {{
        togglePlay(null, currentIdx + 1);
      }}
    }});

    function seek(e) {{
      if (!audio.duration) return;
      const rect = e.currentTarget.getBoundingClientRect();
      audio.currentTime = ((e.clientX - rect.left) / rect.width) * audio.duration;
    }}

    // --- SRT parser ---
    function parseSRT(text) {{
      if (!text) return [];
      const cues = [];
      const blocks = text.trim().split(/\\n\\n+/);
      for (const block of blocks) {{
        const lines = block.split('\\n');
        if (lines.length < 3) continue;
        const times = lines[1].match(/(\\d+):(\\d+):(\\d+)[,.](\\d+)\\s*-->\\s*(\\d+):(\\d+):(\\d+)[,.](\\d+)/);
        if (!times) continue;
        const start = +times[1]*3600 + +times[2]*60 + +times[3] + +times[4]/1000;
        const end = +times[5]*3600 + +times[6]*60 + +times[7] + +times[8]/1000;
        cues.push({{ start, end, text: lines.slice(2).join(' ') }});
      }}
      return cues;
    }}

    // --- Sleep timer ---
    function toggleTimerMenu() {{
      document.getElementById('timerMenu').classList.toggle('show');
    }}

    function setSleepTimer(minutes) {{
      document.getElementById('timerMenu').classList.remove('show');
      const badge = document.getElementById('timerBadge');

      if (sleepTimerId) {{ clearInterval(sleepTimerId); sleepTimerId = null; }}

      if (minutes === 0) {{
        badge.style.display = 'none';
        document.body.classList.remove('dimmed');
        return;
      }}

      sleepRemaining = minutes * 60;
      badge.style.display = 'inline';
      badge.textContent = minutes + 'm';

      sleepTimerId = setInterval(() => {{
        sleepRemaining--;
        const m = Math.ceil(sleepRemaining / 60);
        badge.textContent = m + 'm';

        // dim at 20% remaining
        if (sleepRemaining < minutes * 60 * 0.2) {{
          document.body.classList.add('dimmed');
        }}

        if (sleepRemaining <= 0) {{
          clearInterval(sleepTimerId);
          sleepTimerId = null;
          audio.pause();
          if (currentIdx >= 0) showPauseState(currentIdx, false);
          badge.style.display = 'none';
          // keep dimmed — user is hopefully asleep
        }}
      }}, 1000);
    }}

    // close timer menu on outside click
    document.addEventListener('click', (e) => {{
      if (!e.target.closest('.timer-wrap')) {{
        document.getElementById('timerMenu').classList.remove('show');
      }}
    }});
    </script>
    </body>
    </html>
    """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="生成播客站点（播放器 + RSS 订阅源）")
    parser.add_argument("--base-url", default="", help="音频 URL 前缀（公网部署时使用）")
    parser.add_argument("--serve", action="store_true", help="生成后启动本地 HTTP 服务器并打开浏览器")
    parser.add_argument("--port", type=int, default=8888, help="本地服务器端口（默认 8888）")
    parser.add_argument("--copy-audio", action="store_true",
                        help="把 outputs/ 中的音频复制到 site/audio/，使站点可独立部署（GitHub Pages / Vercel）")
    args = parser.parse_args()

    episodes = scan_episodes(OUTPUTS_DIR)
    # Always produce a site/ — even with 0 episodes — so CI pipelines like
    # GitHub Actions' upload-pages-artifact have a directory to tar. This turns
    # "batch.py had no outputs" into a visible placeholder landing instead of
    # an opaque tar failure.
    SITE_DIR.mkdir(exist_ok=True)

    if not episodes:
        print("[warn] outputs/ 中没有节目——生成占位站点，供 CI/Pages 部署成功")
        placeholder = _build_placeholder_html(args.base_url)
        (SITE_DIR / "index.html").write_text(placeholder, encoding="utf-8")
        (SITE_DIR / "robots.txt").write_text(
            "User-agent: *\nAllow: /\n", encoding="utf-8"
        )
        print(f"[OK] 占位页 → {SITE_DIR / 'index.html'}")
        print("\n下一步：确认 DASHSCOPE_API_KEY 已配置，手动触发 workflow_dispatch 生产第一期")
        return

    if args.copy_audio:
        deploy_audio(episodes, SITE_DIR)
        print(f"[OK] 音频 → {SITE_DIR / 'audio'}（{len(episodes)} 个文件）")

    monetization = load_monetization()
    if monetization:
        src = MONETIZATION_PATH.name if MONETIZATION_PATH.is_file() else MONETIZATION_EXAMPLE_PATH.name
        print(f"[OK] 变现配置 ← {src}")

    # generate HTML player
    html = generate_html(episodes, monetization=monetization, base_url=args.base_url)
    html_path = SITE_DIR / "index.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"[OK] 播放器 → {html_path}")

    # generate per-episode pages (for SEO long-tail traffic)
    episodes_dir = SITE_DIR / "episodes"
    episodes_dir.mkdir(exist_ok=True)
    for i, ep in enumerate(episodes):
        # episodes list is sorted newest-first:
        # "下一集" (newer, chronologically after this one) → earlier index
        # "上一集" (older, chronologically before this one) → later index
        next_ep = episodes[i - 1] if i - 1 >= 0 else None
        prev_ep = episodes[i + 1] if i + 1 < len(episodes) else None
        related = _related_episodes(ep, episodes, k=3)
        page = generate_episode_page(
            ep, monetization, args.base_url, len(episodes),
            prev_ep=prev_ep, next_ep=next_ep, related=related,
        )
        (episodes_dir / f"{_episode_slug(ep)}.html").write_text(page, encoding="utf-8")
    print(f"[OK] 单期页 × {len(episodes)} → {episodes_dir}")

    # generate OG cover images (social share cards) — skip if Pillow unavailable
    if _covers and _covers.available():
        og_dir = SITE_DIR / "og"
        og_dir.mkdir(exist_ok=True)
        generated = 0
        home_cover = og_dir / "home.png"
        if not home_cover.is_file():
            if _covers.generate_home_cover(home_cover, tagline=(monetization or {}).get("brand_tagline") or "每晚 10 分钟，被温柔的声音带入梦境"):
                generated += 1
        for ep in episodes:
            out = og_dir / f"{ep['folder']}.png"
            if out.is_file():
                continue  # covers are immutable per folder name, no regen needed
            if _covers.generate_episode_cover(ep, out):
                generated += 1
        print(f"[OK] OG 封面 → {og_dir}（新生成 {generated} 张，共 {len(episodes) + 1} 张）")
    else:
        print("[skip] OG 封面未生成（Pillow 未安装；pip install Pillow 启用）")

    # generate sitemap.xml + robots.txt so search engines can crawl everything
    (SITE_DIR / "sitemap.xml").write_text(generate_sitemap(episodes, args.base_url), encoding="utf-8")
    (SITE_DIR / "robots.txt").write_text(generate_robots(args.base_url), encoding="utf-8")
    print(f"[OK] sitemap.xml + robots.txt → {SITE_DIR}")

    # generate About page (trust + transparency + theme taxonomy)
    (SITE_DIR / "about.html").write_text(
        generate_about_page(monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] 关于页 → {SITE_DIR / 'about.html'}")

    # generate per-category landing pages (SEO + UX)
    category_dir = SITE_DIR / "category"
    category_dir.mkdir(exist_ok=True)
    cat_generated = 0
    used_cats: set[str] = set()
    for ep in episodes:
        k = (_THEMES.get(ep["theme"]) or {}).get("category")
        if k:
            used_cats.add(k)
    for cat_key in used_cats:
        cat_cfg = (_THEME_CATEGORIES or {}).get(cat_key)
        if not cat_cfg:
            continue
        page = generate_category_page(cat_key, cat_cfg, episodes, monetization, args.base_url)
        (category_dir / f"{cat_key}.html").write_text(page, encoding="utf-8")
        cat_generated += 1
    if cat_generated:
        print(f"[OK] 分类页 × {cat_generated} → {category_dir}")

    # generate RSS feed
    rss = generate_rss(episodes, args.base_url)
    rss_path = SITE_DIR / "feed.xml"
    rss_path.write_text(rss, encoding="utf-8")
    print(f"[OK] RSS 订阅源 → {rss_path}")

    print(f"\n共 {len(episodes)} 期节目已发布。")

    if args.serve:
        # serve from project root so audio paths resolve correctly (in both modes)
        os.chdir(SITE_DIR.parent)
        handler = http.server.SimpleHTTPRequestHandler
        server = http.server.HTTPServer(("", args.port), handler)
        url = f"http://localhost:{args.port}/site/"
        print(f"\n服务器已启动: {url}")
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n服务器已停止。")
            server.shutdown()
    else:
        if args.copy_audio:
            print(f"\n本地预览: cd {SITE_DIR} && python3 -m http.server 8888")
            print(f"部署提示: 直接把 site/ 推送到 GitHub Pages / Vercel 即可上线")
        else:
            print(f"\n本地预览: cd {SITE_DIR.parent} && python3 -m http.server 8888")
            print(f"然后打开: http://localhost:8888/site/")
            print(f"公网部署请加 --copy-audio（让 site/ 包含全部音频）")


if __name__ == "__main__":
    main()
