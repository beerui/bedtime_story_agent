"""publish/pages_episode.py -- generate_episode_page()."""
import json
import re
import textwrap

from .core import (
    PODCAST_AUTHOR,
    PODCAST_LANG,
    PODCAST_TITLE,
    _THEME_CATEGORIES,
    _THEMES,
    _breadcrumb_jsonld,
    _episode_slug,
    _esc,
    _fmt_duration,
    build_share_texts,
    extract_chapters,
)
from .pwa import _pwa_head

# Re-use the same regex pattern (private in core, but needed here)
_STRIP_RE = re.compile(r"\[[^\]]+\]")

from .pages_common import (
    _NEWSLETTER_CSS,
    _NEWSLETTER_JS,
    _build_newsletter_form,
)
from .pages import (
    _build_analytics_head,
    _build_support_html,
    render_script_html,
)


# ---------------------------------------------------------------------------
# generate_episode_page  (~896 lines in original)
# ---------------------------------------------------------------------------

def generate_episode_page(ep: dict, monetization: dict, base_url: str, total_eps: int,
                          prev_ep: dict | None = None, next_ep: dict | None = None,
                          related: list[dict] | None = None) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    page_path = f"episodes/{_episode_slug(ep)}.html"
    canonical = f"{site_url}/{page_path}" if site_url else page_path
    audio_src = f"../audio/{ep['folder']}.mp3" if ep.get("site_audio") else f"../../{ep['audio_path']}"
    audio_abs = f"{site_url}/audio/{ep['folder']}.mp3" if site_url and ep.get("site_audio") else ""
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

    theme_cfg = _THEMES.get(ep["theme"]) or {}
    theme_keywords = theme_cfg.get("search_keywords") or []
    category_key = theme_cfg.get("category")
    category_cfg = _THEME_CATEGORIES.get(category_key) if category_key else None
    category_keywords = category_cfg.get("seo_keywords", []) if category_cfg else []
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
    support_html = _build_support_html(m)

    crumbs: list[tuple[str, str]] = [
        ("助眠电台", f"{site_url}/" if site_url else "../index.html"),
    ]
    if theme_cfg.get("category") and ep.get("theme"):
        theme_url = f"{site_url}/theme/{ep['theme']}.html" if site_url else f"../theme/{ep['theme']}.html"
        crumbs.append((ep["theme"], theme_url))
    crumbs.append((ep["title"], ""))
    breadcrumb_jsonld = _breadcrumb_jsonld(crumbs)

    share_texts = build_share_texts(ep, theme_cfg)

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
    {_pwa_head("../")}
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
    .scene-hero {{
      margin: -8px -20px 24px; overflow: hidden;
      border-radius: 16px;
      box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    }}
    .scene-hero img {{
      width: 100%; display: block;
      max-height: 420px; object-fit: cover; object-position: center;
      filter: saturate(0.88);
    }}
    @media (max-width: 600px) {{
      .scene-hero {{ margin: 0 -16px 20px; border-radius: 12px; }}
      .scene-hero img {{ max-height: 280px; }}
    }}
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
    .support, .affiliates {{
      margin-top: 40px; padding-top: 24px;
      border-top: 1px solid var(--border);
    }}
    .support h2, .affiliates h2 {{
      font-size: 0.92rem; color: var(--text); font-weight: 600;
      margin-bottom: 14px; letter-spacing: 0.02em;
    }}
    .support-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px;
    }}
    .support-tile {{
      display: flex; align-items: center; gap: 12px;
      padding: 14px 16px; border-radius: 12px;
      background: var(--card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .support-tile:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
      transform: translateY(-1px);
    }}
    .support-donation {{ border-color: rgba(240,194,127,0.25); }}
    .support-premium {{ border-color: rgba(124,111,247,0.3); }}
    .support-icon {{ font-size: 1.55rem; line-height: 1; }}
    .support-body {{ flex: 1; min-width: 0; }}
    .support-title {{ font-size: 0.88rem; font-weight: 600; margin-bottom: 2px; }}
    .support-note {{ font-size: 0.72rem; color: var(--dim); line-height: 1.5; }}
    .aff-disclaimer {{
      font-size: 0.7rem; color: var(--dim);
      margin-top: -8px; margin-bottom: 12px; line-height: 1.6;
    }}
    .aff-grid {{
      display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 10px;
    }}
    .aff-card {{
      display: block; padding: 14px; border-radius: 12px;
      background: var(--card); border: 1px solid var(--border);
      color: var(--text); text-decoration: none;
      transition: all 0.25s ease;
    }}
    .aff-card:hover {{
      background: rgba(255,255,255,0.06);
      border-color: rgba(124,111,247,0.28);
    }}
    .aff-emoji {{ font-size: 1.35rem; margin-bottom: 6px; }}
    .aff-title {{ font-size: 0.8rem; font-weight: 600; margin-bottom: 4px; }}
    .aff-desc {{ font-size: 0.7rem; color: var(--dim); line-height: 1.5; }}
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
    .autoadvance {{
      position: fixed; bottom: 30px; left: 50%; transform: translateX(-50%) translateY(20px);
      max-width: 90vw; width: 360px;
      background: linear-gradient(135deg, rgba(20,20,50,0.98), rgba(30,20,60,0.98));
      border: 1px solid rgba(124,111,247,0.4);
      border-radius: 14px; padding: 14px 18px;
      backdrop-filter: blur(12px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.5);
      opacity: 0; transition: all 0.35s ease;
      pointer-events: none;
    }}
    .autoadvance.show {{
      opacity: 1; transform: translateX(-50%) translateY(0);
      pointer-events: auto;
    }}
    .aa-label {{
      font-size: 0.68rem; color: var(--warm);
      letter-spacing: 0.18em; text-transform: uppercase;
      margin-bottom: 4px;
    }}
    .aa-title {{
      font-size: 0.92rem; font-weight: 600; color: var(--text);
      margin-bottom: 10px; line-height: 1.4;
      overflow: hidden; text-overflow: ellipsis;
      display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
    }}
    .aa-row {{
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.78rem;
    }}
    .aa-countdown {{ color: var(--dim); font-variant-numeric: tabular-nums; }}
    .aa-countdown #aaSeconds {{ color: var(--accent); font-weight: 600; }}
    .aa-cancel {{
      background: none; border: 1px solid var(--border);
      color: var(--dim); padding: 4px 12px; border-radius: 14px;
      font-size: 0.72rem; cursor: pointer; font-family: inherit;
    }}
    .aa-cancel:hover {{ color: var(--text); border-color: var(--accent); }}
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
        {'<div class="scene-hero"><img src="../' + _esc(ep["site_scene"]) + '" alt="" loading="lazy"></div>' if ep.get("site_scene") else ''}
        <div class="player">
          <div class="player-controls">
            <div class="speed-wrap">
              <button class="pc-btn" onclick="cycleSpeed(this)" title="播放速度" data-speed="1">
                <span class="pc-label" id="speedLabel">1.0x</span>
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
            <button class="share-btn" onclick="toggleShareMenu()">分享到...</button>
            <a class="share-btn" href="{_esc(audio_src)}" download
               onclick="if(window.trackEvent)window.trackEvent('Download Episode',{{format:'mp3'}});">
              MP3
            </a>
            <a class="share-btn" href="{_esc(_episode_slug(ep))}.txt" download
               onclick="if(window.trackEvent)window.trackEvent('Download Episode',{{format:'txt'}});">
              文稿
            </a>
            <div class="share-menu" id="shareMenu">
              <button onclick="shareTo('x')">X Twitter</button>
              <button onclick="shareTo('weibo')">微博</button>
              <button onclick="shareTo('xhs')">小红书（复制长文）</button>
              <button onclick="shareTo('wechat')">微信（复制链接+文案）</button>
              <button onclick="copyLink()">仅复制链接</button>
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
        {support_html}
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
      <div class="autoadvance" id="autoadvance" hidden>
        <div class="aa-label">下一集</div>
        <div class="aa-title" id="aaTitle"></div>
        <div class="aa-row">
          <div class="aa-countdown"><span id="aaSeconds">10</span> 秒后自动播放</div>
          <button class="aa-cancel" onclick="cancelAutoAdvance()">取消</button>
        </div>
      </div>
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
          window.open('https://twitter.com/intent/tweet?text=' + encodeURIComponent(text) + '&url=' + encodeURIComponent(url), '_blank', 'noopener');
        }} else if (platform === 'weibo') {{
          window.open('https://service.weibo.com/share/share.php?url=' + encodeURIComponent(url) + '&title=' + encodeURIComponent(text), '_blank', 'noopener');
        }} else {{
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
      let _aaTimer = null;
      function scheduleAutoAdvance(nextUrl, nextTitle) {{
        const card = document.getElementById('autoadvance');
        const titleEl = document.getElementById('aaTitle');
        const secEl = document.getElementById('aaSeconds');
        if (!card || !titleEl || !secEl) return;
        titleEl.textContent = nextTitle || '';
        let remain = 10;
        secEl.textContent = remain;
        card.hidden = false;
        card.classList.add('show');
        if (window.trackEvent) window.trackEvent('Auto Advance Offered', {{ next: nextTitle }});
        _aaTimer = setInterval(() => {{
          remain--;
          secEl.textContent = remain;
          if (remain <= 0) {{
            clearInterval(_aaTimer);
            _aaTimer = null;
            if (window.trackEvent) window.trackEvent('Auto Advance Taken', {{ next: nextTitle }});
            location.href = nextUrl + '#autoplay';
          }}
        }}, 1000);
      }}
      function cancelAutoAdvance() {{
        if (_aaTimer) {{ clearInterval(_aaTimer); _aaTimer = null; }}
        const card = document.getElementById('autoadvance');
        if (card) {{ card.classList.remove('show'); card.hidden = true; }}
        if (window.trackEvent) window.trackEvent('Auto Advance Cancelled');
      }}
      if (location.hash.includes('autoplay')) {{
        const autoEl = document.querySelector('.player audio');
        if (autoEl) {{
          const onReady = () => autoEl.play().catch(() => {{}});
          if (autoEl.readyState >= 2) onReady();
          else autoEl.addEventListener('loadedmetadata', onReady, {{ once: true }});
        }}
      }}
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
      (function() {{
        const audioEl = document.querySelector('.player audio');
        if (!audioEl) return;
        const EP_ID = {json.dumps(ep['folder'], ensure_ascii=False)};
        const EP_TITLE = {json.dumps(ep['title'], ensure_ascii=False)};
        const EP_PAGE = location.pathname + location.search;
        const STORAGE_KEY = 'bedtime-last';
        function getResumeTime() {{
          const hashMatch = location.hash.match(/[#&]t=(\\d+(?:\\.\\d+)?)/);
          if (hashMatch) return parseFloat(hashMatch[1]);
          try {{
            const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
            if (saved && saved.ep_id === EP_ID && saved.t > 0) {{
              const ageMs = Date.now() - (saved.ts || 0);
              if (saved.t > 10 && ageMs < 30 * 24 * 3600 * 1000) return saved.t;
            }}
          }} catch (e) {{}}
          return 0;
        }}
        audioEl.addEventListener('loadedmetadata', () => {{
          const t = getResumeTime();
          if (t > 0 && t < audioEl.duration - 5) {{
            audioEl.currentTime = t;
          }}
        }});
        let lastSave = 0;
        audioEl.addEventListener('timeupdate', () => {{
          const now = Date.now();
          if (now - lastSave < 10_000) return;
          lastSave = now;
          if (audioEl.currentTime < 5 || !audioEl.duration) return;
          try {{
            localStorage.setItem(STORAGE_KEY, JSON.stringify({{
              ep_id: EP_ID, title: EP_TITLE, page: EP_PAGE,
              t: audioEl.currentTime, duration: audioEl.duration, ts: now,
            }}));
          }} catch (e) {{}}
        }});
        audioEl.addEventListener('ended', () => {{
          try {{
            const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || 'null');
            if (saved && saved.ep_id === EP_ID) localStorage.removeItem(STORAGE_KEY);
          }} catch (e) {{}}
          {f"scheduleAutoAdvance({json.dumps(_episode_slug(next_ep) + '.html', ensure_ascii=False)}, {json.dumps(next_ep['title'], ensure_ascii=False)});" if next_ep else "// no next episode"}
        }});
        if ('mediaSession' in navigator) {{
          navigator.mediaSession.metadata = new MediaMetadata({{
            title: EP_TITLE,
            artist: {json.dumps(PODCAST_AUTHOR, ensure_ascii=False)},
            album: {json.dumps(PODCAST_TITLE, ensure_ascii=False)},
            artwork: [
              {{ src: {json.dumps(og_image, ensure_ascii=False)}, sizes: '1200x630', type: 'image/png' }},
            ],
          }});
          try {{
            navigator.mediaSession.setActionHandler('play', () => audioEl.play());
            navigator.mediaSession.setActionHandler('pause', () => audioEl.pause());
            navigator.mediaSession.setActionHandler('seekbackward', (e) => {{
              audioEl.currentTime = Math.max(0, audioEl.currentTime - (e.seekOffset || 15));
            }});
            navigator.mediaSession.setActionHandler('seekforward', (e) => {{
              audioEl.currentTime = Math.min(audioEl.duration, audioEl.currentTime + (e.seekOffset || 15));
            }});
            {f"navigator.mediaSession.setActionHandler('previoustrack', () => location.href = {json.dumps(_episode_slug(prev_ep) + '.html', ensure_ascii=False)});" if prev_ep else ""}
            {f"navigator.mediaSession.setActionHandler('nexttrack', () => location.href = {json.dumps(_episode_slug(next_ep) + '.html', ensure_ascii=False)});" if next_ep else ""}
          }} catch (e) {{}}
        }}
      }})();
      const _SPEEDS = [1, 1.25, 1.5, 0.75];
      let _speedIdx = 0;
      function cycleSpeed(btn) {{
        const audioEl = document.querySelector('.player audio');
        if (!audioEl) return;
        _speedIdx = (_speedIdx + 1) % _SPEEDS.length;
        const s = _SPEEDS[_speedIdx];
        audioEl.playbackRate = s;
        btn.querySelector('.pc-label').textContent = s.toFixed(2).replace(/0+$/, '').replace(/\\.$/, '.0') + 'x';
        btn.classList.toggle('active', s !== 1);
        if (window.trackEvent) window.trackEvent('Speed Change', {{ speed: s }});
      }}
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
