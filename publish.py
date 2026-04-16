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

        # Optional LLM-generated chapter titles (replaces generic 引入/深入/尾声)
        chapter_titles: dict = {}
        titles_path = folder / "chapter_titles.json"
        if titles_path.is_file():
            try:
                chapter_titles = json.loads(titles_path.read_text(encoding="utf-8"))
            except Exception:
                pass

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
                "chapter_titles": chapter_titles,
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
            chapters = extract_chapters(
                ep.get("draft_full", ""),
                ep.get("srt", ""),
                title_overrides=ep.get("chapter_titles") or None,
            )
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

def generate_rss(episodes: list[dict], base_url: str,
                  category_key: str = "", category_cfg: dict | None = None) -> str:
    """Generate a Podcast RSS 2.0 XML feed.

    When category_key+category_cfg are given, produces a filtered feed covering
    only episodes whose theme belongs to that category. Channel title/description
    are customized for the category so podcast apps render distinct feeds."""
    ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"
    CONTENT_NS = "http://purl.org/rss/1.0/modules/content/"
    ET.register_namespace("itunes", ITUNES_NS)
    ET.register_namespace("content", CONTENT_NS)

    rss = ET.Element("rss", version="2.0")

    channel = ET.SubElement(rss, "channel")
    if category_key and category_cfg:
        cat_label = category_cfg.get("label", category_key)
        ET.SubElement(channel, "title").text = f"{PODCAST_TITLE} · {cat_label}"
        ET.SubElement(channel, "description").text = category_cfg.get("description", PODCAST_DESC)
        link = f"{base_url.rstrip('/')}/category/{category_key}.html" if base_url else "index.html"
    else:
        ET.SubElement(channel, "title").text = PODCAST_TITLE
        ET.SubElement(channel, "description").text = PODCAST_DESC
        link = base_url or "https://example.com"
    ET.SubElement(channel, "language").text = PODCAST_LANG
    ET.SubElement(channel, "link").text = link
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}author").text = PODCAST_AUTHOR
    ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}explicit").text = "no"
    cat = ET.SubElement(channel, "{http://www.itunes.com/dtds/podcast-1.0.dtd}category")
    cat.set("text", "Health & Fitness")

    # Filter episodes if category_key given
    if category_key:
        episodes = [
            e for e in episodes
            if (_THEMES.get(e.get("theme")) or {}).get("category") == category_key
        ]

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


def _build_newsletter_form(m: dict, context: str = "page") -> str:
    """Render an email newsletter subscription form. Returns empty string when
    monetization.newsletter is absent / disabled / missing endpoint — zero-leak
    when user hasn't configured a provider.

    Compatible with any HTML-form-accepting backend:
    - FormSubmit.co         → https://formsubmit.co/your@email.com
    - FormSubmit alias     → https://formsubmit.co/el/alias-id
    - Buttondown (form)    → https://buttondown.email/api/emails/embed-subscribe/your-username
    - Formspark            → https://submit-form.com/YOUR_FORM_ID
    - Formspree            → https://formspree.io/f/YOUR_FORM_ID

    context is appended to form id/name to avoid collisions when multiple forms
    land on the same page (e.g. homepage hero + about footer)."""
    n = ((m or {}).get("newsletter") or {})
    if not n.get("enabled") or not n.get("endpoint_url"):
        return ""

    title = n.get("title") or "每周收到一封"
    desc = n.get("description") or "每周一封精选助眠内容 + 新期提醒，任何时候可取消。"
    button_label = n.get("button_label") or "订阅"
    success_msg = n.get("success_message") or "订阅成功 · 请查收邮件确认"
    endpoint = n.get("endpoint_url")
    hidden_provider_fields = ""
    # FormSubmit.co benefits from a few standard hidden fields
    if "formsubmit.co" in endpoint:
        hidden_provider_fields = (
            '<input type="hidden" name="_subject" value="助眠电台 · 新订阅请求">'
            '<input type="hidden" name="_template" value="table">'
            '<input type="hidden" name="_captcha" value="false">'
        )
    form_id = f"newsletter-{context}"
    return textwrap.dedent(f"""
    <section class="newsletter" aria-labelledby="{form_id}-title">
      <div class="nl-body">
        <h3 id="{form_id}-title" class="nl-title">{_esc(title)}</h3>
        <p class="nl-desc">{_esc(desc)}</p>
      </div>
      <form class="nl-form" method="POST" action="{_esc(endpoint)}"
            onsubmit="return onNewsletterSubmit(this, event)">
        <input type="email" name="email" required autocomplete="email"
               placeholder="you@example.com" aria-label="邮箱地址">
        <!-- honeypot: bots auto-fill, humans leave empty -->
        <input type="text" name="_honey" style="display:none" tabindex="-1" autocomplete="off">
        {hidden_provider_fields}
        <button type="submit" data-success="{_esc(success_msg)}">{_esc(button_label)}</button>
      </form>
    </section>""")


# JS is identical on every page — inlined in the generated template rather than
# a shared file because we target a zero-JS-build static site. Keep in sync
# with the three render sites (home / episode / about).
_NEWSLETTER_JS = """
function onNewsletterSubmit(form, e) {
  if (window.trackEvent) window.trackEvent('Subscribe Email');
  // Let the native form POST submit (opens provider's success page in same tab).
  // If you want inline success instead, uncomment the block below:
  // e.preventDefault();
  // fetch(form.action, { method: 'POST', body: new FormData(form) })
  //   .then(r => r.ok ? form.querySelector('button').textContent = form.querySelector('button').dataset.success : null)
  //   .catch(() => {});
  return true;
}
"""

_NEWSLETTER_CSS = """
.newsletter {
  margin: 28px 0; padding: 18px 22px;
  background: linear-gradient(135deg, rgba(240,194,127,0.06), rgba(124,111,247,0.04));
  border: 1px solid rgba(240,194,127,0.2);
  border-radius: 14px;
  display: grid; gap: 10px;
}
.nl-title { font-size: 0.92rem; font-weight: 600; color: #f0c27f; letter-spacing: 0.02em; }
.nl-desc { font-size: 0.78rem; color: #9a9ab0; line-height: 1.6; }
.nl-form { display: flex; gap: 8px; flex-wrap: wrap; }
.nl-form input[type="email"] {
  flex: 1 1 200px; min-width: 180px;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  color: #d4d4e0; padding: 8px 14px;
  border-radius: 18px; font-size: 0.82rem;
  font-family: inherit;
}
.nl-form input[type="email"]:focus {
  outline: none; border-color: rgba(124,111,247,0.5);
  background: rgba(255,255,255,0.07);
}
.nl-form button {
  padding: 8px 20px; border-radius: 18px;
  background: linear-gradient(135deg, #7c6ff7, #9b6ff7);
  border: none; color: #fff;
  font-size: 0.82rem; font-family: inherit; cursor: pointer;
  transition: transform 0.2s ease;
}
.nl-form button:hover { transform: translateY(-1px); }
"""


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

    # WebSite schema with SearchAction → eligible for Google sitelinks searchbox
    website_jsonld = {
        "@context": "https://schema.org",
        "@type": "WebSite",
        "name": PODCAST_TITLE,
        "url": site_url or "/",
    }
    if site_url:
        website_jsonld["potentialAction"] = {
            "@type": "SearchAction",
            "target": {
                "@type": "EntryPoint",
                "urlTemplate": f"{site_url}/?q={{search_term_string}}",
            },
            "query-input": "required name=search_term_string",
        }

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
    <script type="application/ld+json">{json.dumps(website_jsonld, ensure_ascii=False)}</script>
    {_build_analytics_head(m)}""")


import re


_PHASE_RE = re.compile(r"\[阶段[:：]\s*([^\]]+)\]")
_PAUSE_RE = re.compile(r"\[停顿[^\]]*\]")
_CUE_RE = re.compile(r"\[环境音[:：]\s*([^\]]+)\]")
_STRIP_RE = re.compile(r"\[[^\]]+\]")


def render_script_plaintext(text: str, chapter_titles: dict | None = None) -> str:
    """Convert a story draft to clean plain-text suitable for TXT download.

    - Phase markers become '【引入】' style headings (using chapter_titles if
      provided, else just the phase name)
    - Ambient cues become parentheticals (（雨声）)
    - Pause markers and prosody tags are stripped
    - Empty lines collapse into paragraph breaks"""
    if not text:
        return ""
    out: list[str] = []
    overrides = chapter_titles or {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if out and out[-1] != "":
                out.append("")
            continue
        m = _PHASE_RE.match(line)
        if m:
            phase = m.group(1).strip()
            title = overrides.get(phase) or phase
            if out and out[-1] != "":
                out.append("")
            out.append(f"【{title}】")
            out.append("")
            continue
        line = _CUE_RE.sub(lambda mm: f"（{mm.group(1).strip()}）", line)
        line = _PAUSE_RE.sub("", line)
        line = _STRIP_RE.sub("", line).strip()
        if line:
            out.append(line)
    # strip leading/trailing empties
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


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


def generate_episodes_manifest(episodes: list[dict], base_url: str) -> str:
    """Machine-readable episode index — for 3rd-party embeds, future mobile apps,
    aggregators, search APIs. One JSON file at /episodes.json containing normalized
    per-episode metadata aligned with the site's canonical URLs."""
    base = (base_url or "").rstrip("/")
    out = {
        "site": {
            "name": PODCAST_TITLE,
            "description": PODCAST_DESC,
            "language": PODCAST_LANG,
            "url": base or None,
            "rss": f"{base}/feed.xml" if base else "feed.xml",
        },
        "categories": {
            k: {
                "label": c.get("label", k),
                "description": c.get("description", ""),
                "rss": f"{base}/feed/{k}.xml" if base else f"feed/{k}.xml",
                "page": f"{base}/category/{k}.html" if base else f"category/{k}.html",
            }
            for k, c in (_THEME_CATEGORIES or {}).items()
        },
        "episodes": [],
    }
    for ep in episodes:
        theme_cfg = _THEMES.get(ep["theme"]) or {}
        slug = _episode_slug(ep)
        page_url = f"{base}/episodes/{slug}.html" if base else f"episodes/{slug}.html"
        audio_rel = ep.get("site_audio") or ep.get("audio_path", "")
        audio_url = f"{base}/{audio_rel}" if base and audio_rel else audio_rel
        chapters = extract_chapters(
            ep.get("draft_full", ""),
            ep.get("srt", ""),
            title_overrides=ep.get("chapter_titles") or None,
        )
        out["episodes"].append({
            "id": ep["folder"],
            "title": ep["title"],
            "theme": ep["theme"],
            "category": theme_cfg.get("category"),
            "pain_point": theme_cfg.get("pain_point"),
            "technique": theme_cfg.get("technique"),
            "emotional_target": theme_cfg.get("emotional_target"),
            "description": ep["description"],
            "tags": ep["tags"],
            "duration_sec": ep["duration"],
            "word_count": ep["word_count"],
            "published_at": ep["timestamp"].strftime("%Y-%m-%dT%H:%M:%S"),
            "page_url": page_url,
            "audio_url": audio_url,
            "transcript_url": f"{base}/episodes/{slug}.txt" if base else f"episodes/{slug}.txt",
            "chapters": [
                {"title": c["title"], "phase": c.get("phase"),
                 "start_sec": round(c["start_sec"], 2), "end_sec": round(c["end_sec"], 2)}
                for c in chapters
            ],
        })
    return json.dumps(out, ensure_ascii=False, indent=2)


def _breadcrumb_jsonld(items: list[tuple[str, str]]) -> str:
    """Build a BreadcrumbList JSON-LD string. items is ordered list of (name, url).
    Empty URL at the tail item means "current page" (no link)."""
    if not items:
        return ""
    list_items = []
    for i, (name, url) in enumerate(items, start=1):
        entry = {"@type": "ListItem", "position": i, "name": name}
        if url:
            entry["item"] = url
        list_items.append(entry)
    data = {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": list_items,
    }
    return f'<script type="application/ld+json">{json.dumps(data, ensure_ascii=False)}</script>'


def extract_chapters(story_text: str, srt_text: str, title_overrides: dict | None = None) -> list[dict]:
    """Build chapter list by correlating [阶段：X] markers in the story with
    SRT cue timestamps. Returns [{title, start_sec, end_sec}]. Empty list if
    either input is missing or no phases detected.

    title_overrides: optional mapping {phase_name: friendly_title} to rename
    generic "引入/深入/尾声" to LLM-generated specific titles.

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
        # Prefer LLM-generated specific title, fall back to phase name
        display_title = (title_overrides or {}).get(name) or name
        chapters.append({"title": display_title, "phase": name, "start_sec": start, "end_sec": end})
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
    newsletter_html = _build_newsletter_form(m, context="episode")

    # BreadcrumbList for SEO: Home → theme → this episode
    crumbs: list[tuple[str, str]] = [
        ("助眠电台", f"{site_url}/" if site_url else "../index.html"),
    ]
    if theme_cfg.get("category") and ep.get("theme"):
        theme_url = f"{site_url}/theme/{ep['theme']}.html" if site_url else f"../theme/{ep['theme']}.html"
        crumbs.append((ep["theme"], theme_url))
    crumbs.append((ep["title"], ""))  # current page, no link
    breadcrumb_jsonld = _breadcrumb_jsonld(crumbs)

    # Pre-filled share copy per platform — empowers fans to 1-click share with
    # platform-appropriate formatting (short for X/Weibo, long for XHS).
    pain_for_share = (theme_cfg.get("pain_point", "") or "").strip()
    tech_for_share = (theme_cfg.get("technique", "") or "").split("：")[0].strip() or "心理学助眠技术"
    share_texts = {
        "x": f"{ep['title']}｜{PODCAST_TITLE}\n{pain_for_share}—用 {tech_for_share} 引导。",
        "weibo": f"#助眠电台# 【{ep['theme']}】{ep['title']}\n{pain_for_share}\n用{tech_for_share}——{ep['word_count']}字 · {_fmt_duration(ep['duration'])}",
        "xhs": (
            f"【{ep['theme']}】{ep['title']}\n\n"
            f"✨ 此刻的感受：{pain_for_share}\n"
            f"🧠 使用的技术：{theme_cfg.get('technique', '助眠冥想')}\n"
            f"🌙 听后的状态：{theme_cfg.get('emotional_target', '放松入眠')}\n\n"
            f"时长 {_fmt_duration(ep['duration'])}，AI 生成但心理学锚点手工设计。"
            f"\n\n#助眠 #失眠 #冥想 #{ep['theme']} #心理学"
        ),
        "wechat": f"{ep['title']} | {PODCAST_TITLE}\n{pain_for_share}",
    }

    # Chapters — one per [阶段：X] marker. Renders as clickable navigation below
    # the player so returning listeners can jump to e.g. the body-scan section.
    chapters = extract_chapters(
        ep.get("draft_full", ""),
        ep.get("srt", ""),
        title_overrides=ep.get("chapter_titles") or None,
    )
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
    {breadcrumb_jsonld}
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
    .player-controls {{
      display: flex; gap: 8px; margin-bottom: 10px;
      justify-content: flex-end;
    }}
    .speed-wrap, .timer-wrap {{ position: relative; }}
    .pc-btn {{
      background: rgba(255,255,255,0.03); border: 1px solid var(--border);
      color: var(--text); padding: 6px 12px; border-radius: 18px;
      cursor: pointer; font-size: 0.78rem; font-family: inherit;
      display: inline-flex; align-items: center; gap: 6px;
      transition: all 0.2s ease;
    }}
    .pc-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .pc-btn.active {{
      border-color: var(--warm); color: var(--warm);
      background: rgba(240,194,127,0.08);
    }}
    .pc-label {{ font-variant-numeric: tabular-nums; }}
    .pc-timer-menu {{
      position: absolute; top: 100%; right: 0; margin-top: 6px;
      background: rgba(20,20,50,0.97); border: 1px solid var(--border);
      border-radius: 10px; padding: 6px 0; min-width: 120px;
      display: none; z-index: 5;
    }}
    .pc-timer-menu.show {{ display: block; }}
    .pc-timer-menu button {{
      display: block; width: 100%; text-align: left;
      padding: 7px 14px; background: none; border: none;
      color: var(--text); font-size: 0.78rem; cursor: pointer;
      font-family: inherit;
    }}
    .pc-timer-menu button:hover {{ background: rgba(255,255,255,0.05); }}
    .pc-timer-badge {{
      font-size: 0.64rem; color: var(--warm);
      background: rgba(240,194,127,0.15);
      padding: 1px 6px; border-radius: 8px;
    }}
    body.pc-dimmed {{ opacity: 0.3; transition: opacity 1.5s ease; }}
    .share-wrap {{
      position: relative; margin-top: 12px;
      display: flex; flex-wrap: wrap; gap: 8px;
    }}
    a.share-btn {{ text-decoration: none; display: inline-flex; align-items: center; }}
    .share-btn {{
      background: none; border: 1px solid var(--border);
      color: var(--text); padding: 6px 14px; border-radius: 18px;
      cursor: pointer; font-size: 0.78rem; font-family: inherit;
      transition: all 0.2s;
    }}
    .share-btn:hover {{ border-color: var(--accent); color: var(--accent); }}
    .share-menu {{
      position: absolute; top: 100%; left: 0; margin-top: 6px;
      background: rgba(20,20,50,0.97); border: 1px solid var(--border);
      border-radius: 10px; padding: 6px 0; min-width: 200px;
      display: none; z-index: 5;
    }}
    .share-menu.show {{ display: block; }}
    .share-menu button {{
      display: block; width: 100%; text-align: left;
      padding: 8px 16px; background: none; border: none;
      color: var(--text); font-size: 0.82rem; cursor: pointer;
      font-family: inherit;
    }}
    .share-menu button:hover {{ background: rgba(255,255,255,0.06); color: var(--accent); }}
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

    {_NEWSLETTER_CSS}

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
        {'<a class="theme-badge" href="../theme/' + _esc(ep['theme']) + '.html">' if theme_cfg.get('category') else '<span class="theme-badge">'}{_esc(ep['theme'])}{'</a>' if theme_cfg.get('category') else '</span>'}
        <h1>{_esc(ep['title'])}</h1>
        <div class="meta">{ep['timestamp'].strftime('%Y-%m-%d')} · {ep['word_count']} 字 · {_fmt_duration(ep['duration'])}</div>
        <div class="tags">{tags_html}</div>

        <div class="player">
          <div class="player-controls">
            <div class="speed-wrap">
              <button class="pc-btn" onclick="cycleSpeed(this)" title="播放速度" data-speed="1">
                <span class="pc-label" id="speedLabel">1.0×</span>
              </button>
            </div>
            <div class="timer-wrap" id="timerWrap">
              <button class="pc-btn" onclick="togglePcTimerMenu()" title="睡眠定时器">
                <svg width="16" height="16" viewBox="0 0 24 24" style="vertical-align:-3px">
                  <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" stroke-width="2"/>
                  <polyline points="12,7 12,12 16,14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
                </svg>
                <span id="pcTimerBadge" class="pc-timer-badge" style="display:none"></span>
              </button>
              <div class="pc-timer-menu" id="pcTimerMenu">
                <button onclick="setPcSleepTimer(0)">关闭</button>
                <button onclick="setPcSleepTimer(15)">15 分钟</button>
                <button onclick="setPcSleepTimer(30)">30 分钟</button>
                <button onclick="setPcSleepTimer(45)">45 分钟</button>
                <button onclick="setPcSleepTimer(60)">60 分钟</button>
              </div>
            </div>
          </div>
          <audio controls preload="metadata" src="{_esc(audio_src)}"></audio>
          <div class="share-wrap">
            <button class="share-btn" onclick="toggleShareMenu()">📤 分享到…</button>
            <a class="share-btn" href="{_esc(audio_src)}" download
               onclick="if(window.trackEvent)window.trackEvent('Download Episode',{{format:'mp3'}});">
              ⬇︎ MP3
            </a>
            <a class="share-btn" href="{_esc(_episode_slug(ep))}.txt" download
               onclick="if(window.trackEvent)window.trackEvent('Download Episode',{{format:'txt'}});">
              📄 文稿
            </a>
            <div class="share-menu" id="shareMenu">
              <button onclick="shareTo('x')">𝕏 Twitter</button>
              <button onclick="shareTo('weibo')">微博</button>
              <button onclick="shareTo('xhs')">小红书（复制长文）</button>
              <button onclick="shareTo('wechat')">微信（复制链接+文案）</button>
              <button onclick="copyLink()">🔗 仅复制链接</button>
            </div>
          </div>
        </div>

        {chapters_html}

        {tech_badge_html}

        {'<div class="summary">' + _esc(desc_plain) + '</div>' if desc_plain else ''}

        <article class="transcript">
          {transcript_html}
        </article>

        {nav_html}

        {newsletter_html}

        {related_html}

        <div class="footer-nav">
          <a href="../index.html">← 所有 {total_eps} 期</a>
          <a href="../themes.html">全部主题</a>
          <a href="../faq.html">FAQ</a>
          <a href="../about.html">关于</a>
          <a href="../feed.xml">RSS 订阅 →</a>
        </div>
      </div>

      <div class="toast" id="toast">已复制</div>
      <script>
      const SHARE_TEXTS = {json.dumps(share_texts, ensure_ascii=False)};

      function toggleShareMenu() {{
        document.getElementById('shareMenu').classList.toggle('show');
      }}
      document.addEventListener('click', (e) => {{
        if (!e.target.closest('.share-wrap')) {{
          document.getElementById('shareMenu')?.classList.remove('show');
        }}
      }});

      function shareTo(platform) {{
        const url = location.href;
        const text = SHARE_TEXTS[platform] || '';
        const fullText = text + '\\n\\n' + url;
        if (window.trackEvent) window.trackEvent('Share Episode', {{ platform }});
        document.getElementById('shareMenu').classList.remove('show');
        if (platform === 'x') {{
          // X / Twitter share intent — auto-fill tweet
          window.open('https://twitter.com/intent/tweet?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(url), '_blank', 'noopener');
        }} else if (platform === 'weibo') {{
          // Weibo share — their intent URL
          window.open('https://service.weibo.com/share/share.php?url=' + encodeURIComponent(url) + '&title=' + encodeURIComponent(text), '_blank', 'noopener');
        }} else {{
          // XHS and WeChat: no web share intent, copy full text for paste
          navigator.clipboard.writeText(fullText).then(() => {{
            const t = document.getElementById('toast');
            t.textContent = platform === 'xhs' ? '小红书文案已复制，去粘贴发帖' : '已复制（链接+文案）';
            t.classList.add('show');
            setTimeout(() => {{
              t.classList.remove('show');
              t.textContent = '已复制';
            }}, 2200);
          }});
        }}
      }}

      function copyLink() {{
        if (window.trackEvent) window.trackEvent('Share Episode', {{ platform: 'copy_link' }});
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

      // --- Playback speed cycle ---
      const _SPEEDS = [1, 1.25, 1.5, 0.75];
      let _speedIdx = 0;
      function cycleSpeed(btn) {{
        const audioEl = document.querySelector('.player audio');
        if (!audioEl) return;
        _speedIdx = (_speedIdx + 1) % _SPEEDS.length;
        const s = _SPEEDS[_speedIdx];
        audioEl.playbackRate = s;
        btn.querySelector('.pc-label').textContent = s.toFixed(2).replace(/0+$/, '').replace(/\.$/, '.0') + '×';
        btn.classList.toggle('active', s !== 1);
        if (window.trackEvent) window.trackEvent('Speed Change', {{ speed: s }});
      }}

      // --- Sleep timer (single-episode page) ---
      let _pcTimerId = null;
      let _pcTimerRemain = 0;
      function togglePcTimerMenu() {{
        document.getElementById('pcTimerMenu').classList.toggle('show');
      }}
      document.addEventListener('click', (e) => {{
        if (!e.target.closest('#timerWrap')) {{
          document.getElementById('pcTimerMenu')?.classList.remove('show');
        }}
      }});
      function setPcSleepTimer(minutes) {{
        const menu = document.getElementById('pcTimerMenu');
        const badge = document.getElementById('pcTimerBadge');
        const audioEl = document.querySelector('.player audio');
        menu?.classList.remove('show');
        if (_pcTimerId) {{ clearInterval(_pcTimerId); _pcTimerId = null; }}
        if (minutes === 0) {{
          badge.style.display = 'none';
          document.body.classList.remove('pc-dimmed');
          return;
        }}
        _pcTimerRemain = minutes * 60;
        badge.style.display = 'inline';
        badge.textContent = minutes + 'm';
        if (window.trackEvent) window.trackEvent('Sleep Timer Set', {{ minutes }});
        _pcTimerId = setInterval(() => {{
          _pcTimerRemain--;
          badge.textContent = Math.ceil(_pcTimerRemain / 60) + 'm';
          if (_pcTimerRemain < minutes * 60 * 0.2) document.body.classList.add('pc-dimmed');
          if (_pcTimerRemain <= 0) {{
            clearInterval(_pcTimerId); _pcTimerId = null;
            audioEl?.pause();
            badge.style.display = 'none';
          }}
        }}, 1000);
      }}

      // Tiny trackEvent shim if analytics block didn't inject one
      if (!window.trackEvent) {{
        window.trackEvent = function(n, p) {{
          try {{
            if (window.plausible) window.plausible(n, p ? {{ props: p }} : undefined);
            else if (window.umami) window.umami.track(n, p || {{}});
            else if (window.gtag) window.gtag('event', n, p || {{}});
          }} catch (e) {{}}
        }};
      }}

      {_NEWSLETTER_JS}
      </script>
    </body>
    </html>
    """)


def generate_theme_page(theme_name: str, theme_cfg: dict, episodes: list[dict],
                         monetization: dict, base_url: str) -> str:
    """Single-theme focused page — targets the theme's search_keywords for
    long-tail SEO, and surfaces the psychological framework (pain/technique/
    target) so visitors arriving from a search can immediately see whether
    this matches their need."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    cat_key = theme_cfg.get("category", "")
    cat_cfg = (_THEME_CATEGORIES or {}).get(cat_key) or {}
    canonical = f"{site_url}/theme/{theme_name}.html" if site_url else f"theme/{theme_name}.html"
    og_image = f"{site_url}/og/home.png" if site_url else "../og/home.png"
    analytics_head = _build_analytics_head(m)

    # Breadcrumbs: Home → Themes hub → Category (if any) → this theme
    _home_url = f"{site_url}/" if site_url else "../index.html"
    _themes_url = f"{site_url}/themes.html" if site_url else "../themes.html"
    crumbs = [("助眠电台", _home_url), ("全部主题", _themes_url)]
    if cat_key:
        _cat_url = f"{site_url}/category/{cat_key}.html" if site_url else f"../category/{cat_key}.html"
        crumbs.append((cat_cfg.get("label", cat_key), _cat_url))
    crumbs.append((theme_name, ""))
    breadcrumb_jsonld = _breadcrumb_jsonld(crumbs)

    pain = theme_cfg.get("pain_point", "").strip()
    technique = theme_cfg.get("technique", "").strip()
    target = theme_cfg.get("emotional_target", "").strip()
    ideal_min = theme_cfg.get("ideal_duration_min", 0) or 0
    keywords = theme_cfg.get("search_keywords", []) or []
    description = (pain or "") + "。" + (technique or "")

    # Episodes of this theme
    theme_eps = [e for e in episodes if e.get("theme") == theme_name]

    # Related themes: other themes in same category
    related = []
    for nm, cfg in (_THEMES or {}).items():
        if nm == theme_name:
            continue
        if cfg.get("category") != cat_key:
            continue
        related.append((nm, cfg))

    ep_cards: list[str] = []
    if theme_eps:
        for ep in theme_eps:
            tags_html = "".join(f'<span class="tag">{_esc(t)}</span>' for t in ep["tags"][:3])
            ep_cards.append(f"""
          <a class="ep-card" href="../episodes/{_esc(_episode_slug(ep))}.html">
            <div class="ep-head">
              <span class="ep-date">{ep['timestamp'].strftime('%Y-%m-%d')}</span>
              <span class="ep-meta">{_fmt_duration(ep['duration'])}</span>
            </div>
            <h3 class="ep-title">{_esc(ep['title'])}</h3>
            <p class="ep-desc">{_esc((ep.get('description') or '')[:100])}</p>
            <div class="ep-tags">{tags_html}</div>
          </a>""")
    else:
        ep_cards.append('<p class="empty-note">此主题暂无节目——下次生产会补齐。</p>')

    related_cards: list[str] = []
    for nm, cfg in related[:4]:
        rp = cfg.get("pain_point", "")[:48]
        related_cards.append(
            f'<a class="rel-theme" href="{_esc(nm)}.html">'
            f'<div class="rel-name">{_esc(nm)}</div>'
            f'<div class="rel-pain">{_esc(rp)}</div></a>'
        )

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(theme_name)} · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="{_esc(description[:160])}">
    <meta name="keywords" content="{_esc(','.join(keywords + [theme_name, '助眠', '睡眠']))}">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="{_esc(theme_name)} · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="{_esc(description[:160])}">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {breadcrumb_jsonld}
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
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 36px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.82rem; }}
    .back:hover {{ color: var(--accent); }}
    .cat-badge {{
      display: inline-block;
      font-size: 0.72rem; color: var(--accent);
      background: rgba(124,111,247,0.12);
      padding: 3px 12px; border-radius: 20px;
      text-decoration: none; margin: 18px 0 10px;
    }}
    h1 {{
      font-size: 1.8rem; margin-bottom: 12px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .spec {{
      background: linear-gradient(135deg, rgba(124,111,247,0.06), rgba(240,194,127,0.03));
      border: 1px solid rgba(124,111,247,0.18);
      border-radius: 14px; padding: 18px 22px;
      margin: 20px 0 32px; display: grid; gap: 10px;
    }}
    .spec-row {{ display: flex; gap: 14px; font-size: 0.88rem; line-height: 1.6; }}
    .spec-label {{
      color: var(--warm); font-weight: 500;
      min-width: 92px; flex-shrink: 0;
    }}
    .spec-val {{ color: var(--text); flex: 1; }}
    h2 {{
      font-size: 1.05rem; font-weight: 600;
      margin: 32px 0 12px;
      border-left: 3px solid var(--accent); padding-left: 10px;
    }}
    .ep-card {{
      display: block; padding: 14px 18px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; margin-bottom: 10px;
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .ep-card:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.3);
    }}
    .ep-head {{ display: flex; justify-content: space-between; margin-bottom: 6px; }}
    .ep-date {{ font-size: 0.72rem; color: var(--warm); font-family: ui-monospace, Menlo, monospace; }}
    .ep-meta {{ font-size: 0.72rem; color: var(--dim); }}
    .ep-title {{ font-size: 0.95rem; font-weight: 600; margin-bottom: 4px; }}
    .ep-desc {{ font-size: 0.82rem; color: var(--dim); margin-bottom: 6px; }}
    .ep-tags {{ display: flex; gap: 6px; flex-wrap: wrap; }}
    .tag {{
      font-size: 0.68rem; color: var(--dim);
      background: rgba(255,255,255,0.05);
      padding: 1px 7px; border-radius: 10px;
    }}
    .rel-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 10px;
    }}
    .rel-theme {{
      display: block; padding: 12px 16px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .rel-theme:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.3);
    }}
    .rel-name {{ font-size: 0.88rem; font-weight: 600; margin-bottom: 4px; }}
    .rel-pain {{ font-size: 0.74rem; color: var(--dim); }}
    .empty-note {{
      color: var(--dim); text-align: center; padding: 30px 16px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px;
    }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 0.8rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="../index.html">← 全部节目</a>
        <a class="cat-badge" href="../category/{_esc(cat_key)}.html">{_esc(cat_cfg.get('label', cat_key))}</a>
        <h1>{_esc(theme_name)}</h1>

        <section class="spec">
          {'<div class="spec-row"><span class="spec-label">此刻感受</span><span class="spec-val">' + _esc(pain) + '</span></div>' if pain else ''}
          {'<div class="spec-row"><span class="spec-label">使用技术</span><span class="spec-val">' + _esc(technique) + '</span></div>' if technique else ''}
          {'<div class="spec-row"><span class="spec-label">听后状态</span><span class="spec-val">' + _esc(target) + '</span></div>' if target else ''}
          {'<div class="spec-row"><span class="spec-label">推荐时长</span><span class="spec-val">' + str(ideal_min) + ' 分钟</span></div>' if ideal_min else ''}
        </section>

        <h2>本主题节目（{len(theme_eps)} 期）</h2>
        {''.join(ep_cards)}

        {'<h2>同分类其他主题</h2><div class="rel-grid">' + ''.join(related_cards) + '</div>' if related_cards else ''}

        <div class="footer">
          <a href="../themes.html">全部主题</a>
          <a href="../category/{_esc(cat_key)}.html">{_esc(cat_cfg.get('label', cat_key))} 分类</a>
          <a href="../index.html">首页</a>
          <a href="../about.html">关于</a>
          <a href="../feed.xml">RSS</a>
        </div>
      </div>
    </body>
    </html>
    """)


def generate_themes_hub(monetization: dict, base_url: str) -> str:
    """Master taxonomy page listing all 18 themes grouped by 4 categories."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/themes.html" if site_url else "themes.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("全部主题", ""),
    ])

    sections: list[str] = []
    for cat_key, cat_cfg in (_THEME_CATEGORIES or {}).items():
        items = []
        for nm, cfg in (_THEMES or {}).items():
            if cfg.get("category") != cat_key:
                continue
            pain = cfg.get("pain_point", "")[:48]
            items.append(
                f'<a class="theme-item" href="theme/{_esc(nm)}.html">'
                f'<div class="t-name">{_esc(nm)}</div>'
                f'<div class="t-pain">{_esc(pain)}</div></a>'
            )
        if not items:
            continue
        sections.append(f"""
        <section class="cat-section">
          <a class="cat-header" href="category/{_esc(cat_key)}.html">
            <h2>{_esc(cat_cfg.get('label', cat_key))}</h2>
            <span class="cat-count">{len(items)} 个主题 →</span>
          </a>
          <p class="cat-desc">{_esc(cat_cfg.get('description', ''))}</p>
          <div class="t-grid">{''.join(items)}</div>
        </section>""")

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>全部主题 · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="18 个主题，4 大分类——按搜索意图或痛点浏览所有助眠主题。">
    <meta name="keywords" content="助眠主题,助眠分类,失眠,ACT,认知解离,裁员焦虑,AI焦虑,相亲压力,父母健康,失恋">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:title" content="全部主题 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="18 个主题，4 大分类——按搜索意图或痛点浏览所有助眠主题。">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {breadcrumb_jsonld}
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
    .wrap {{ max-width: 820px; margin: 0 auto; padding: 40px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 1.8rem; margin: 18px 0 8px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 0.95rem; margin-bottom: 32px; }}
    .cat-section {{ margin-bottom: 40px; }}
    .cat-header {{
      display: flex; justify-content: space-between; align-items: baseline;
      color: var(--text); text-decoration: none;
      border-left: 3px solid var(--accent); padding-left: 10px;
      margin-bottom: 8px;
    }}
    .cat-header:hover h2 {{ color: var(--accent); }}
    .cat-header h2 {{ font-size: 1.05rem; font-weight: 600; }}
    .cat-count {{ font-size: 0.78rem; color: var(--dim); }}
    .cat-desc {{ font-size: 0.85rem; color: var(--dim); margin-bottom: 14px; padding-left: 13px; }}
    .t-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .theme-item {{
      display: block; padding: 14px 16px;
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .theme-item:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.3);
      transform: translateY(-1px);
    }}
    .t-name {{ font-size: 0.9rem; font-weight: 600; margin-bottom: 5px; }}
    .t-pain {{ font-size: 0.74rem; color: var(--dim); line-height: 1.5; }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>全部主题</h1>
        <p class="lede">18 个主题，按「你此刻的感受」分 4 类——找到最贴合的那一条路径。</p>
        {''.join(sections)}
      </div>
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
    # Absolute URL for category RSS — needed for podcast app subscribe
    cat_feed_abs = f"{site_url}/feed/{cat_key}.xml" if site_url else f"../feed/{cat_key}.xml"
    cat_feed_rel = f"../feed/{cat_key}.xml"
    analytics_head = _build_analytics_head(m)

    # Breadcrumbs: Home → Themes hub → [this category]
    _home_url = f"{site_url}/" if site_url else "../index.html"
    _themes_url = f"{site_url}/themes.html" if site_url else "../themes.html"
    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", _home_url),
        ("全部主题", _themes_url),
        (label, ""),
    ])

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
    <link rel="alternate" type="application/rss+xml" title="{_esc(label)} RSS" href="{_esc(cat_feed_rel)}">
    {breadcrumb_jsonld}
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
    .cat-subscribe {{
      margin-top: 14px; display: flex; flex-wrap: wrap;
      align-items: center; gap: 10px;
      padding: 10px 14px;
      background: rgba(124,111,247,0.06);
      border: 1px solid rgba(124,111,247,0.2);
      border-radius: 10px;
      font-size: 0.78rem;
    }}
    .cat-subscribe .sub-label {{ color: var(--warm); }}
    .cat-rss-link, .cat-rss-copy {{
      color: var(--accent); text-decoration: none;
      background: none; border: 1px solid rgba(124,111,247,0.3);
      padding: 3px 10px; border-radius: 12px;
      font-family: inherit; font-size: 0.75rem;
      cursor: pointer; transition: all 0.2s;
    }}
    .cat-rss-link:hover, .cat-rss-copy:hover {{
      background: rgba(124,111,247,0.12); color: var(--text);
    }}
    .cat-rss-copy.copied {{ border-color: var(--warm); color: var(--warm); }}
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
          <div class="cat-subscribe">
            <span class="sub-label">订阅本分类 RSS ·</span>
            <a class="cat-rss-link" href="{_esc(cat_feed_rel)}" target="_blank" rel="noopener">打开 feed.xml</a>
            <button class="cat-rss-copy" onclick="copyCatFeed()" type="button">复制 URL</button>
          </div>
        </header>
        <main>
          {''.join(cards)}
        </main>
        <div class="footer">
          <a href="../index.html">全部节目</a>
          <a href="../about.html">关于</a>
          <a href="../feed.xml">全站 RSS</a>
          <a href="../themes.html">全部主题</a>
        </div>
      </div>
      <script>
      function copyCatFeed() {{
        const url = {json.dumps(cat_feed_abs, ensure_ascii=False)};
        navigator.clipboard.writeText(url).then(() => {{
          const btn = document.querySelector('.cat-rss-copy');
          const old = btn.textContent;
          btn.textContent = '已复制';
          btn.classList.add('copied');
          setTimeout(() => {{ btn.textContent = old; btn.classList.remove('copied'); }}, 1600);
        }});
      }}
      </script>
    </body>
    </html>
    """)


def generate_stats_page(episodes: list[dict], monetization: dict, base_url: str) -> str:
    """Public content-library stats page — transparency signal + SEO freshness.

    Reads episodes + THEMES, computes per-category counts, per-theme counts,
    total runtime, most-recent publish date, gaps (themes with 0 episodes).
    Pure HTML/CSS bars, no JS libraries."""
    import datetime as _dt
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/stats.html" if site_url else "stats.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("数据", ""),
    ])

    total_eps = len(episodes)
    total_sec = sum(e.get("duration", 0) for e in episodes)
    total_hours = total_sec / 3600
    total_words = sum(e.get("word_count", 0) for e in episodes)

    # Category breakdown
    cat_counts: dict[str, int] = {}
    for ep in episodes:
        k = (_THEMES.get(ep["theme"]) or {}).get("category") or "其他"
        cat_counts[k] = cat_counts.get(k, 0) + 1

    # Theme coverage (present vs configured)
    configured_themes = set((_THEMES or {}).keys())
    produced_themes = {ep["theme"] for ep in episodes}
    missing_themes = sorted(configured_themes - produced_themes)

    # Theme counts — sorted descending
    theme_counts: dict[str, int] = {}
    for ep in episodes:
        theme_counts[ep["theme"]] = theme_counts.get(ep["theme"], 0) + 1
    theme_top = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

    # Freshness
    latest = max((e["timestamp"] for e in episodes), default=None)
    latest_str = latest.strftime("%Y-%m-%d %H:%M") if latest else "—"
    days_since = (_dt.datetime.now() - latest).days if latest else None

    # Weekly cadence — last 8 weeks
    weeks: dict[str, int] = {}
    if episodes:
        for ep in episodes:
            iso_year, iso_week, _ = ep["timestamp"].isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            weeks[key] = weeks.get(key, 0) + 1
    recent_weeks = sorted(weeks.items())[-8:]

    # Category section HTML
    max_cat = max(cat_counts.values()) if cat_counts else 1
    cat_rows: list[str] = []
    for cat_key, cat_cfg in (_THEME_CATEGORIES or {}).items():
        n = cat_counts.get(cat_key, 0)
        width_pct = (n / max_cat) * 100 if max_cat else 0
        label = cat_cfg.get("label", cat_key)
        cat_rows.append(
            f'<div class="row"><span class="row-label"><a href="category/{_esc(cat_key)}.html">{_esc(label)}</a></span>'
            f'<div class="bar-track"><div class="bar" style="width:{width_pct:.1f}%">{n}</div></div></div>'
        )

    # Top themes
    max_theme = theme_top[0][1] if theme_top else 1
    theme_rows: list[str] = []
    for name, n in theme_top[:10]:
        width_pct = (n / max_theme) * 100 if max_theme else 0
        theme_rows.append(
            f'<div class="row"><span class="row-label"><a href="theme/{_esc(name)}.html">{_esc(name)}</a></span>'
            f'<div class="bar-track"><div class="bar bar-theme" style="width:{width_pct:.1f}%">{n}</div></div></div>'
        )

    # Weekly activity
    max_week = max((n for _, n in recent_weeks), default=1) or 1
    week_rows: list[str] = []
    for label, n in recent_weeks:
        h_pct = (n / max_week) * 100
        week_rows.append(
            f'<div class="week-col"><div class="week-bar" style="height:{h_pct:.0f}%" title="{n} 期"></div>'
            f'<div class="week-label">{_esc(label[-3:])}</div></div>'
        )

    # Missing themes
    missing_html = ""
    if missing_themes:
        missing_chips = "".join(
            f'<a class="missing-theme" href="theme/{_esc(t)}.html">{_esc(t)}</a>'
            for t in missing_themes
        )
        missing_html = (
            '<section><h2>暂无节目的主题</h2>'
            '<p class="tip">这些主题配置了完整心理学锚点，等待后续生产——主题页已提前就位以便种 SEO 长尾。</p>'
            f'<div class="missing-grid">{missing_chips}</div></section>'
        )

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>数据 · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="助眠电台的内容库公开数据：{total_eps} 期节目、{total_hours:.1f} 小时总时长、4 分类覆盖度、生产节奏。">
    <meta name="keywords" content="助眠电台 数据,助眠 内容库,节目统计,播客统计">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="数据 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="{total_eps} 期节目 · {total_hours:.1f} 小时 · 4 分类">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    {breadcrumb_jsonld}
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
    h1 {{
      font-size: 1.8rem; margin: 18px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 0.95rem; margin-bottom: 32px; }}
    .big-numbers {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
      gap: 12px; margin-bottom: 36px;
    }}
    .big-card {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 14px; padding: 18px 20px;
    }}
    .big-val {{
      font-size: 1.8rem; font-weight: 700;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      font-variant-numeric: tabular-nums;
    }}
    .big-label {{ font-size: 0.74rem; color: var(--dim); margin-top: 2px; }}
    h2 {{
      font-size: 1.05rem; font-weight: 600;
      margin: 32px 0 14px;
      border-left: 3px solid var(--accent); padding-left: 10px;
    }}
    .row {{
      display: grid; grid-template-columns: 140px 1fr; gap: 12px;
      align-items: center; margin-bottom: 8px;
    }}
    .row-label {{ font-size: 0.84rem; }}
    .row-label a {{ color: var(--text); text-decoration: none; }}
    .row-label a:hover {{ color: var(--accent); }}
    .bar-track {{
      background: rgba(255,255,255,0.03); height: 24px; border-radius: 6px;
      overflow: hidden; position: relative;
    }}
    .bar {{
      height: 100%; background: linear-gradient(90deg, var(--accent), #9b6ff7);
      padding-right: 8px; color: #fff; font-size: 0.72rem;
      display: flex; align-items: center; justify-content: flex-end;
      min-width: 28px; transition: width 0.4s ease;
    }}
    .bar-theme {{ background: linear-gradient(90deg, var(--warm), #e3a45a); color: #06061a; }}
    .weeks {{
      display: flex; gap: 10px; align-items: flex-end;
      height: 120px; padding: 10px 0; margin-bottom: 12px;
    }}
    .week-col {{ flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6px; }}
    .week-bar {{
      width: 100%; max-width: 32px; min-height: 2px;
      background: linear-gradient(to top, var(--accent), var(--warm));
      border-radius: 4px 4px 0 0;
    }}
    .week-label {{
      font-size: 0.66rem; color: var(--dim);
      font-family: ui-monospace, Menlo, monospace;
    }}
    .tip {{ color: var(--dim); font-size: 0.82rem; margin-bottom: 12px; }}
    .missing-grid {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .missing-theme {{
      font-size: 0.76rem; color: var(--dim);
      background: var(--card); border: 1px dashed var(--border);
      padding: 4px 10px; border-radius: 14px;
      text-decoration: none;
    }}
    .missing-theme:hover {{ color: var(--accent); border-color: var(--accent); }}
    .fresh {{
      font-size: 0.88rem; color: var(--text);
      background: var(--card); border: 1px solid var(--border);
      border-radius: 10px; padding: 12px 16px;
    }}
    .fresh strong {{ color: var(--warm); }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 0.82rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>内容库数据</h1>
        <p class="lede">透明比宣传更可信——下面是这个电台完整的内容库公开快照。</p>

        <div class="big-numbers">
          <div class="big-card"><div class="big-val">{total_eps}</div><div class="big-label">期节目</div></div>
          <div class="big-card"><div class="big-val">{total_hours:.1f}</div><div class="big-label">小时总时长</div></div>
          <div class="big-card"><div class="big-val">{total_words:,}</div><div class="big-label">字累计剧本</div></div>
          <div class="big-card"><div class="big-val">{len(produced_themes)}/{len(configured_themes)}</div><div class="big-label">主题已产出</div></div>
        </div>

        <section>
          <h2>分类覆盖</h2>
          {''.join(cat_rows)}
        </section>

        <section>
          <h2>主题热度 Top 10</h2>
          {''.join(theme_rows)}
        </section>

        <section>
          <h2>最近 8 周生产节奏</h2>
          <div class="weeks">{''.join(week_rows) or '<p class="tip">还没足够数据——至少要跑 1 周才能看趋势。</p>'}</div>
        </section>

        <section>
          <h2>最新一期</h2>
          <p class="fresh">
            <strong>{_esc(latest_str)}</strong>
            {f' · 距今 {days_since} 天' if days_since is not None else ''}
            {' · 新鲜' if days_since is not None and days_since <= 2 else (' · 该更新了' if days_since is not None and days_since >= 7 else '')}
          </p>
        </section>

        {missing_html}

        <div class="footer">
          <a href="index.html">首页</a>
          <a href="about.html">关于</a>
          <a href="themes.html">全部主题</a>
          <a href="faq.html">FAQ</a>
          <a href="episodes.json">episodes.json</a>
          <a href="feed.xml">RSS</a>
        </div>
      </div>
    </body>
    </html>
    """)


def generate_faq_page(monetization: dict, base_url: str) -> str:
    """FAQ page with inline FAQPage JSON-LD — eligible for Google rich snippets.

    Covers the skeptical-visitor funnel questions (AI-generated? Does it work?
    How to subscribe? How you make money?) — answers directly feed the search
    engine's "People also ask" panel."""
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    canonical = f"{site_url}/faq.html" if site_url else "faq.html"
    og_image = f"{site_url}/og/home.png" if site_url else "og/home.png"
    analytics_head = _build_analytics_head(m)

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("FAQ", ""),
    ])

    qa_pairs = [
        (
            "这些助眠故事是 AI 生成的吗？能信吗？",
            "是。剧本由 Qwen 大模型生成，分三轮（大纲 → 扩写 → 润色），每篇完成后走 5 维 100 分制质量评估，低于 70 自动按反馈重写一次。每个主题都有明确的心理学锚点（痛点 / 技术 / 目标状态）注入 prompt——不是随机生成，而是按专业框架产出。生产流程完全透明，见关于页。"
        ),
        (
            "真的能帮我入睡吗？依据是什么？",
            "基于循证心理学技术：ACT 认知解离（停止反刍思维）、Safe Place Imagery（安全岛意象）、Autogenic Training（自律训练法诱发副交感神经）、Body Scan（躯体扫描）、心理退行（回到低心理负荷的童年状态）。每一类主题对应一种技术。音频用韵律弧线引擎把语速从 1.0× 渐变到 0.55×，音量从 1.0 降到 0.3，模拟真人催眠师的节奏变化。"
        ),
        (
            "一集多长合适？",
            "推荐 10-15 分钟。每个主题都声明了 ideal_duration_min（见主题页）：快速放松类 10 分钟，完整身体扫描类 15 分钟，情绪共鸣类 11 分钟。入睡前听 1-2 集即可。"
        ),
        (
            "怎么订阅到播客 App？",
            "首页订阅区可以一键：Apple Podcasts 用 podcasts:// 协议直接唤起本机播客 App 订阅，无需提交目录；Spotify / 小宇宙 / Overcast / Bilibili 等按钮会跳到对应页面（如已配置）；RSS 按钮直接复制 feed 地址到任何播客 App。"
        ),
        (
            "为什么不同主题用不同声音？",
            "每个主题在 THEME_VOICE_MAP 匹配了合适的音色：男声沉稳用于职场/AI 焦虑/失业类（像过来人陪伴），女声温柔用于情感疗愈类（承接情绪）。TTS 优先使用阿里 CosyVoice（自然度高），配额耗尽自动降级到免费的 edge-tts（微软语音）。"
        ),
        (
            "你们怎么挣钱？",
            "透明披露（详见关于页）：打赏（一次性小额）、联盟商品推广（睡眠相关耳塞/眼罩/白噪音机，你不会多花钱）、品牌赞助位（出现会明确标注）、未来的会员内容（长版/无 BGM 纯人声版）。所有变现位都不会影响内容的心理学质量。"
        ),
        (
            "可以用手机听吗？会耗流量吗？",
            "可以。音频是标准 MP3，每期 3-5MB。推荐订阅到 Apple Podcasts / Pocket Casts 等 App 并在 WiFi 下预下载，出门时离线听不耗流量。网页播放器也支持 SRT 字幕跟读。"
        ),
        (
            "节目什么时候更新？",
            "北京时间每天 07:05 自动生产并部署一期新节目。18 个主题会在配置的 cron 触发时随机选（可以把 --themes 改成固定名单做连续主题）。RSS/小宇宙/Apple Podcasts 订阅会自动推送新期。"
        ),
        (
            "如何给反馈或建议？",
            "联系邮箱见关于页。也欢迎在 GitHub 源码仓库开 issue（项目完全开源）。建议特别关注：哪个主题最帮助你入睡、哪个阶段（引入/深入/尾声）最有效——这些数据会指导后续主题设计。"
        ),
    ]

    # FAQPage JSON-LD for Google rich results
    faq_jsonld = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a},
            }
            for q, a in qa_pairs
        ],
    }

    qa_html = "".join(
        f'<details class="qa"><summary>{_esc(q)}</summary><p>{_esc(a)}</p></details>'
        for q, a in qa_pairs
    )

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>常见问题 · {_esc(PODCAST_TITLE)}</title>
    <meta name="description" content="关于 AI 生成、心理学依据、订阅、变现、节目时长的常见问题解答。">
    <meta name="keywords" content="助眠 常见问题,AI 生成 助眠,助眠 心理学,播客 订阅,失眠 FAQ">
    <link rel="canonical" href="{_esc(canonical)}">
    <meta property="og:type" content="article">
    <meta property="og:title" content="常见问题 · {_esc(PODCAST_TITLE)}">
    <meta property="og:description" content="AI 生成可信吗？心理学依据是什么？怎么订阅？变现怎么做？">
    <meta property="og:image" content="{_esc(og_image)}">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:image" content="{_esc(og_image)}">
    <script type="application/ld+json">{json.dumps(faq_jsonld, ensure_ascii=False)}</script>
    {breadcrumb_jsonld}
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
    .wrap {{ max-width: 720px; margin: 0 auto; padding: 40px 20px 80px; }}
    .back {{ color: var(--dim); text-decoration: none; font-size: 0.85rem; }}
    .back:hover {{ color: var(--accent); }}
    h1 {{
      font-size: 1.8rem; margin: 18px 0 10px;
      background: linear-gradient(135deg, var(--warm), var(--accent));
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }}
    .lede {{ color: var(--dim); font-size: 0.95rem; margin-bottom: 32px; }}
    .qa {{
      background: var(--card); border: 1px solid var(--border);
      border-radius: 12px; padding: 0; margin-bottom: 12px;
      transition: all 0.2s ease;
    }}
    .qa[open] {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.25);
    }}
    .qa summary {{
      cursor: pointer; padding: 14px 18px;
      font-size: 0.92rem; font-weight: 600;
      list-style: none; position: relative;
      padding-right: 44px;
    }}
    .qa summary::-webkit-details-marker {{ display: none; }}
    .qa summary::after {{
      content: '+'; position: absolute; right: 18px; top: 50%;
      transform: translateY(-50%); color: var(--accent); font-size: 1.2rem;
      transition: transform 0.3s ease;
    }}
    .qa[open] summary::after {{ transform: translateY(-50%) rotate(45deg); }}
    .qa p {{
      padding: 0 18px 16px; color: var(--text);
      font-size: 0.87rem; line-height: 1.8;
    }}
    .footer {{
      margin-top: 40px; padding-top: 20px;
      border-top: 1px solid var(--border);
      display: flex; flex-wrap: wrap; gap: 14px;
      font-size: 0.82rem; color: var(--dim);
    }}
    .footer a {{ color: var(--dim); text-decoration: none; }}
    .footer a:hover {{ color: var(--accent); }}
    </style>
    </head>
    <body>
      <div class="wrap">
        <a class="back" href="index.html">← 回到首页</a>
        <h1>常见问题</h1>
        <p class="lede">AI 生成的助眠音频需要回答的真实问题——透明比安慰更能建立信任。</p>
        {qa_html}
        <div class="footer">
          <a href="index.html">首页</a>
          <a href="about.html">关于</a>
          <a href="themes.html">全部主题</a>
          <a href="feed.xml">RSS</a>
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

    breadcrumb_jsonld = _breadcrumb_jsonld([
        ("助眠电台", f"{site_url}/" if site_url else "index.html"),
        ("关于", ""),
    ])

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

    newsletter_html = _build_newsletter_form(m, context="about")

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
    {breadcrumb_jsonld}
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

    {_NEWSLETTER_CSS}

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

        {newsletter_html}

        {contact_html}
      </div>
      <script>
      {_NEWSLETTER_JS}
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
        # Category-specific RSS feed
        floc = f"{base}/feed/{ck}.xml" if base else f"feed/{ck}.xml"
        urls.append(f"""  <url>
    <loc>{floc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.6</priority>
  </url>""")
    # theme pages — one per configured theme with a category
    for theme_name, theme_cfg in (_THEMES or {}).items():
        if not theme_cfg.get("category"):
            continue
        tloc = f"{base}/theme/{theme_name}.html" if base else f"theme/{theme_name}.html"
        urls.append(f"""  <url>
    <loc>{tloc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.65</priority>
  </url>""")
    # themes taxonomy hub
    if _THEMES and _THEME_CATEGORIES:
        themes_loc = f"{base}/themes.html" if base else "themes.html"
        urls.append(f"""  <url>
    <loc>{themes_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.7</priority>
  </url>""")
    about_loc = f"{base}/about.html" if base else "about.html"
    urls.append(f"""  <url>
    <loc>{about_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    faq_loc = f"{base}/faq.html" if base else "faq.html"
    urls.append(f"""  <url>
    <loc>{faq_loc}</loc>
    <changefreq>monthly</changefreq>
    <priority>0.6</priority>
  </url>""")
    stats_loc = f"{base}/stats.html" if base else "stats.html"
    urls.append(f"""  <url>
    <loc>{stats_loc}</loc>
    <changefreq>weekly</changefreq>
    <priority>0.5</priority>
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
        theme_cfg_ep = _THEMES.get(ep["theme"]) or {}
        cat_attr = theme_cfg_ep.get("category", "")
        # Flat lowercase search index: title + theme + pain_point + tags + desc
        search_parts = [
            ep.get("title", ""),
            ep.get("theme", ""),
            theme_cfg_ep.get("pain_point", ""),
            theme_cfg_ep.get("technique", ""),
            " ".join(ep.get("tags", [])),
            ep.get("description", ""),
        ]
        search_idx = " ".join(p for p in search_parts if p).lower()
        # Escape quotes for safe HTML attribute use
        search_idx = html_mod.escape(search_idx, quote=True)

        episode_cards.append(f"""
      <article class="episode" data-audio="{audio_src}" data-cat="{cat_attr}" data-search="{search_idx}"{srt_attr}>
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
    newsletter_html = _build_newsletter_form(monetization or {}, context="home")

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

    {_NEWSLETTER_CSS}

    /* --- search box --- */
    .search-box {{
      display: flex; align-items: center; gap: 12px;
      margin-bottom: 16px;
    }}
    .search-box input[type="search"] {{
      flex: 1;
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 10px 16px;
      border-radius: 20px;
      font-size: 0.85rem;
      font-family: inherit;
    }}
    .search-box input[type="search"]:focus {{
      outline: none;
      border-color: rgba(124,111,247,0.5);
      background: rgba(255,255,255,0.06);
    }}
    .search-stats {{
      font-size: 0.72rem; color: var(--text-dim);
      min-width: 60px; text-align: right;
    }}
    .episode.hide-by-search {{ display: none; }}

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
          <a class="stats-link" href="themes.html">主题 →</a>
          <a class="stats-link" href="stats.html">数据 →</a>
          <a class="stats-link" href="faq.html">FAQ →</a>
          <a class="stats-link" href="about.html">关于 →</a>
        </div>
      </header>

      {subscribe_html}

      {newsletter_html}

      <div class="search-box">
        <input type="search" id="searchInput" placeholder="🔍 搜索主题、痛点或关键词…"
               aria-label="搜索节目" autocomplete="off">
        <span class="search-stats" id="searchStats"></span>
      </div>

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

    // --- Client-side search (title/theme/pain_point/tags/desc) ---
    (function() {{
      const input = document.getElementById('searchInput');
      const stats = document.getElementById('searchStats');
      const eps = document.querySelectorAll('.episode');
      if (!input || !eps.length) return;

      let debounce;
      let lastQueryTracked = '';
      function apply() {{
        const q = input.value.trim().toLowerCase();
        let shown = 0, total = eps.length;
        eps.forEach(ep => {{
          const idx = ep.dataset.search || '';
          const match = !q || idx.includes(q);
          ep.classList.toggle('hide-by-search', !match);
          if (match && !ep.classList.contains('hide-by-filter')) shown++;
        }});
        stats.textContent = q ? `${{shown}}/${{total}}` : '';
        // Track non-trivial queries (≥2 chars, not same as last)
        if (q.length >= 2 && q !== lastQueryTracked) {{
          clearTimeout(debounce);
          debounce = setTimeout(() => {{
            if (window.trackEvent) window.trackEvent('Search Query', {{ q: q.slice(0, 40) }});
            lastQueryTracked = q;
          }}, 800);
        }}
      }}
      input.addEventListener('input', apply);
      // Re-apply when a category chip flips (so search + filter compose)
      document.querySelectorAll('.filter-chips .chip').forEach(c => {{
        c.addEventListener('click', () => setTimeout(apply, 0));
      }});
      // Deep-link: ?q=... auto-fills search (supports Google sitelinks searchbox)
      const urlQ = new URLSearchParams(location.search).get('q');
      if (urlQ) {{ input.value = urlQ; apply(); }}
    }})();

    {_NEWSLETTER_JS}

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
        # Write clean plain-text transcript alongside the HTML — downloadable as TXT
        plain = render_script_plaintext(ep.get("draft_full", ""), ep.get("chapter_titles"))
        if plain:
            (episodes_dir / f"{_episode_slug(ep)}.txt").write_text(plain, encoding="utf-8")
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

    # generate FAQ page (FAQPage schema for rich results)
    (SITE_DIR / "faq.html").write_text(
        generate_faq_page(monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] FAQ 页 → {SITE_DIR / 'faq.html'}")

    # generate stats page (public content-library dashboard)
    (SITE_DIR / "stats.html").write_text(
        generate_stats_page(episodes, monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] 数据页 → {SITE_DIR / 'stats.html'}")

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

    # generate per-theme landing pages (one per configured theme, covers themes
    # without episodes so the taxonomy is complete even pre-content)
    theme_dir = SITE_DIR / "theme"
    theme_dir.mkdir(exist_ok=True)
    theme_generated = 0
    for theme_name, theme_cfg in (_THEMES or {}).items():
        if not theme_cfg.get("category"):
            continue  # skip legacy/custom themes without metadata
        page = generate_theme_page(theme_name, theme_cfg, episodes, monetization, args.base_url)
        (theme_dir / f"{theme_name}.html").write_text(page, encoding="utf-8")
        theme_generated += 1
    if theme_generated:
        print(f"[OK] 主题页 × {theme_generated} → {theme_dir}")

    # themes taxonomy hub (one page linking to all themes grouped by category)
    if _THEMES and _THEME_CATEGORIES:
        (SITE_DIR / "themes.html").write_text(
            generate_themes_hub(monetization, args.base_url), encoding="utf-8"
        )
        print(f"[OK] 主题总览 → {SITE_DIR / 'themes.html'}")

    # generate RSS feed
    rss = generate_rss(episodes, args.base_url)
    rss_path = SITE_DIR / "feed.xml"
    rss_path.write_text(rss, encoding="utf-8")
    print(f"[OK] RSS 订阅源 → {rss_path}")

    # generate per-category RSS feeds — subscribers can follow just their interest
    if used_cats and _THEME_CATEGORIES:
        feed_dir = SITE_DIR / "feed"
        feed_dir.mkdir(exist_ok=True)
        feeds_written = 0
        for cat_key in used_cats:
            cat_cfg = _THEME_CATEGORIES.get(cat_key)
            if not cat_cfg:
                continue
            cat_rss = generate_rss(episodes, args.base_url, cat_key, cat_cfg)
            (feed_dir / f"{cat_key}.xml").write_text(cat_rss, encoding="utf-8")
            feeds_written += 1
        if feeds_written:
            print(f"[OK] 分类 RSS × {feeds_written} → {feed_dir}")

    # machine-readable manifest for 3rd-party consumers
    (SITE_DIR / "episodes.json").write_text(
        generate_episodes_manifest(episodes, args.base_url), encoding="utf-8"
    )
    print(f"[OK] episodes.json → {SITE_DIR / 'episodes.json'}")

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
