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
    to GitHub Pages / Vercel / Netlify without needing outputs/ alongside."""
    audio_out = site_dir / "audio"
    audio_out.mkdir(parents=True, exist_ok=True)
    for ep in episodes:
        dest_name = f"{ep['folder']}.mp3"
        dest = audio_out / dest_name
        src = Path(ep["audio_abs"])
        if not dest.is_file() or dest.stat().st_mtime < src.stat().st_mtime:
            shutil.copy2(src, dest)
        ep["site_audio"] = f"audio/{dest_name}"


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


def _build_head_meta(episodes: list[dict], m: dict, base_url: str) -> str:
    site_url = (m.get("site_url") or base_url or "").rstrip("/")
    tagline = _esc(m.get("brand_tagline") or PODCAST_DESC)
    og_url = site_url or ""
    feed_url = f"{site_url}/feed.xml" if site_url else "feed.xml"

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
    {'<meta property="og:url" content="' + _esc(og_url) + '">' if og_url else ''}
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="{_esc(PODCAST_TITLE)}">
    <meta name="twitter:description" content="{tagline}">
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
    site_url = (m.get("site_url") or base_url or "").rstrip("/")
    page_path = f"episodes/{_episode_slug(ep)}.html"
    canonical = f"{site_url}/{page_path}" if site_url else page_path
    # audio path: episode pages live in site/episodes/, audio in site/audio/ → ../audio/
    audio_src = f"../audio/{ep['folder']}.mp3" if ep.get("site_audio") else f"../../{ep['audio_path']}"
    audio_abs = f"{site_url}/audio/{ep['folder']}.mp3" if site_url and ep.get("site_audio") else ""

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

    share_text = f"{ep['title']} | {PODCAST_TITLE}"
    analytics_head = _build_analytics_head(m)

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
    <meta name="keywords" content="{_esc('助眠,睡眠,冥想,' + ','.join(ep['tags'][:5]))}">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{_esc(ep['title'])}">
    <meta property="og:description" content="{_esc(desc_plain[:160])}">
    <meta property="og:locale" content="zh_CN">
    {'<meta property="og:url" content="' + _esc(canonical) + '">' if site_url else ''}
    <meta name="twitter:card" content="summary">
    <meta name="twitter:title" content="{_esc(ep['title'])}">
    <meta name="twitter:description" content="{_esc(desc_plain[:160])}">
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
        <span class="theme-badge">{_esc(ep['theme'])}</span>
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

        {'<div class="summary">' + _esc(desc_plain) + '</div>' if desc_plain else ''}

        <article class="transcript">
          {transcript_html}
        </article>

        {nav_html}

        {related_html}

        <div class="footer-nav">
          <a href="../index.html">← 所有 {total_eps} 期</a>
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
      </script>
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

        episode_cards.append(f"""
      <article class="episode" data-audio="{audio_src}"{srt_attr}>
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
    }}
    .stats b {{ color: var(--warm); font-weight: 600; }}

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
        </div>
      </header>

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
    }});

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
    if not episodes:
        print("outputs/ 中没有找到可用的音频内容。先运行 python3 batch.py --count 1 --audio-only")
        return

    # create site/
    SITE_DIR.mkdir(exist_ok=True)

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

    # generate sitemap.xml + robots.txt so search engines can crawl everything
    (SITE_DIR / "sitemap.xml").write_text(generate_sitemap(episodes, args.base_url), encoding="utf-8")
    (SITE_DIR / "robots.txt").write_text(generate_robots(args.base_url), encoding="utf-8")
    print(f"[OK] sitemap.xml + robots.txt → {SITE_DIR}")

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
