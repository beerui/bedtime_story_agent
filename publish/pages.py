#!/usr/bin/env python3
"""HTML page generators -- shared helpers + homepage."""
import html as html_mod
import json
import re
import textwrap

from .core import (
    PODCAST_AUTHOR,
    PODCAST_DESC,
    PODCAST_LANG,
    PODCAST_TITLE,
    _THEME_CATEGORIES,
    _THEMES,
    _episode_href,
    _esc,
    _fmt_duration,
    resolve_html_audio,
)
from .pwa import _pwa_head
from .pages_common import (
    _NEWSLETTER_CSS,
    _NEWSLETTER_JS,
    _build_newsletter_form,
    _build_placeholder_html,
)

# Re-use the same regex patterns (private in core, but needed here for render_script_*)
_PHASE_RE = re.compile(r"\[阶段[:：]\s*([^\]]+)\]")
_PAUSE_RE = re.compile(r"\[停顿[^\]]*\]")
_CUE_RE = re.compile(r"\[环境音[:：]\s*([^\]]+)\]")
_STRIP_RE = re.compile(r"\[[^\]]+\]")


# ---------------------------------------------------------------------------
# Subscription / support / newsletter / analytics HTML fragments
# ---------------------------------------------------------------------------

def _build_subscribe_html(m: dict, feed_url: str) -> str:
    sub = (m or {}).get("subscribe") or {}
    feed_url = feed_url or "feed.xml"
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
    {_pwa_head("")}
    <script type="application/ld+json">{json.dumps(jsonld, ensure_ascii=False)}</script>
    <script type="application/ld+json">{json.dumps(website_jsonld, ensure_ascii=False)}</script>
    {_build_analytics_head(m)}""")


def _build_analytics_head(m: dict) -> str:
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


# ---------------------------------------------------------------------------
# Script rendering (plain-text and HTML)
# ---------------------------------------------------------------------------

def render_script_plaintext(text: str, chapter_titles: dict | None = None) -> str:
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
    while out and out[0] == "":
        out.pop(0)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out)


def render_script_html(text: str) -> str:
    if not text:
        return ""

    sections: list[tuple[str, list[str]]] = []
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

        line = _CUE_RE.sub(lambda m: f"__CUE__{m.group(1).strip()}__ECUE__", line)
        parts = _PAUSE_RE.split(line)
        for idx, seg in enumerate(parts):
            clean = _STRIP_RE.sub("", seg).strip()
            if clean:
                current_buf.append(clean)
            if idx < len(parts) - 1:
                flush_paragraph()

    flush_section()

    html_parts: list[str] = []
    for phase, paras in sections:
        if phase:
            html_parts.append(f'<h2 class="phase">{_esc(phase)}</h2>')
        for p in paras:
            safe = _esc(p)
            safe = safe.replace("__CUE__", '<em class="cue">（').replace("__ECUE__", "）</em>")
            html_parts.append(f"<p>{safe}</p>")
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# generate_html  (homepage)
# ---------------------------------------------------------------------------

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

    # Category filter chips -- only render when a category has at least 1 episode
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

    /* --- continue listening card (returning-visitor resume) --- */
    .continue-listening {{
      display: flex; align-items: center; gap: 12px;
      margin-bottom: 28px;
      padding: 14px 18px;
      background: linear-gradient(135deg, rgba(240,194,127,0.09), rgba(124,111,247,0.05));
      border: 1px solid rgba(240,194,127,0.28);
      border-radius: 14px;
    }}
    .continue-listening[hidden] {{ display: none; }}
    .cl-body {{ flex: 1; min-width: 0; }}
    .cl-label {{
      font-size: 0.7rem; color: var(--warm);
      letter-spacing: 0.15em; text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .cl-title {{
      display: block; font-size: 0.98rem; font-weight: 600;
      color: var(--text); text-decoration: none;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }}
    .cl-title:hover {{ color: var(--accent); }}
    .cl-progress {{
      margin-top: 8px; height: 3px;
      background: rgba(255,255,255,0.08); border-radius: 2px; overflow: hidden;
    }}
    .cl-fill {{ height: 100%; background: linear-gradient(90deg, var(--warm), var(--accent)); }}
    .cl-time {{
      margin-top: 4px; font-size: 0.7rem; color: var(--text-dim);
      font-variant-numeric: tabular-nums;
    }}
    .cl-dismiss {{
      background: none; border: none; color: var(--text-dim);
      font-size: 1rem; cursor: pointer; padding: 6px 10px;
      transition: color 0.2s;
    }}
    .cl-dismiss:hover {{ color: var(--text); }}

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

      <section class="continue-listening" id="continueCard" hidden>
        <div class="cl-body">
          <div class="cl-label">继续收听</div>
          <a class="cl-title" id="clTitle" href="#"></a>
          <div class="cl-progress"><div class="cl-fill" id="clFill"></div></div>
          <div class="cl-time" id="clTime"></div>
        </div>
        <button class="cl-dismiss" onclick="dismissContinue()" title="不再显示">✕</button>
      </section>

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
        // Track non-trivial queries (>=2 chars, not same as last)
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

    // --- Register service worker for PWA offline support ---
    if ('serviceWorker' in navigator) {{
      window.addEventListener('load', () => {{
        navigator.serviceWorker.register('sw.js').catch(() => {{}});
      }});
    }}

    // --- Continue listening card ---
    function dismissContinue() {{
      try {{ localStorage.removeItem('bedtime-last'); }} catch (e) {{}}
      document.getElementById('continueCard').hidden = true;
      if (window.trackEvent) window.trackEvent('Dismiss Continue Card');
    }}
    (function() {{
      let saved;
      try {{ saved = JSON.parse(localStorage.getItem('bedtime-last') || 'null'); }}
      catch (e) {{ return; }}
      if (!saved || !saved.ep_id || !saved.t || !saved.duration) return;
      const ageH = (Date.now() - (saved.ts || 0)) / (3600 * 1000);
      if (ageH > 48) return;  // stale
      const pct = saved.t / saved.duration;
      if (pct < 0.05 || pct > 0.92) return;  // too fresh or near-done
      const card = document.getElementById('continueCard');
      const titleA = document.getElementById('clTitle');
      if (!card || !titleA) return;
      titleA.textContent = saved.title || '未命名';
      const page = saved.page || `episodes/${{saved.ep_id}}.html`;
      titleA.href = page + (page.includes('#') ? '&' : '#') + 't=' + Math.floor(saved.t);
      document.getElementById('clFill').style.width = (pct * 100).toFixed(1) + '%';
      const fmtT = (s) => {{
        s = Math.floor(s); const m = Math.floor(s/60);
        return m + ':' + String(s%60).padStart(2,'0');
      }};
      document.getElementById('clTime').textContent = fmtT(saved.t) + ' / ' + fmtT(saved.duration) + ' · ' + Math.floor(ageH) + 'h 前';
      card.hidden = false;
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
          // keep dimmed -- user is hopefully asleep
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
