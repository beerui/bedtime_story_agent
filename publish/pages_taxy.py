"""publish/pages_taxy.py -- theme, category, and stats page generators."""
import datetime as _dt
import json
import textwrap

from .core import (
    PODCAST_TITLE,
    _THEME_CATEGORIES,
    _THEMES,
    _breadcrumb_jsonld,
    _episode_slug,
    _esc,
    _fmt_duration,
)
from .pwa import _pwa_head
from .pages import _build_analytics_head


# ---------------------------------------------------------------------------
# generate_theme_page
# ---------------------------------------------------------------------------

def generate_theme_page(theme_name: str, theme_cfg: dict, episodes: list[dict],
                         monetization: dict, base_url: str) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    cat_key = theme_cfg.get("category", "")
    cat_cfg = (_THEME_CATEGORIES or {}).get(cat_key) or {}
    canonical = f"{site_url}/theme/{theme_name}.html" if site_url else f"theme/{theme_name}.html"
    og_image = f"{site_url}/og/home.png" if site_url else "../og/home.png"
    analytics_head = _build_analytics_head(m)

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

    theme_eps = [e for e in episodes if e.get("theme") == theme_name]

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


# ---------------------------------------------------------------------------
# generate_themes_hub
# ---------------------------------------------------------------------------

def generate_themes_hub(monetization: dict, base_url: str) -> str:
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
    {_pwa_head("")}
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


# ---------------------------------------------------------------------------
# generate_category_page
# ---------------------------------------------------------------------------

def generate_category_page(cat_key: str, cat_cfg: dict, episodes: list[dict],
                            monetization: dict, base_url: str) -> str:
    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    label = cat_cfg.get("label", cat_key)
    desc = cat_cfg.get("description", "")
    seo_keywords = cat_cfg.get("seo_keywords", [])
    canonical = f"{site_url}/category/{cat_key}.html" if site_url else f"category/{cat_key}.html"
    og_image = f"{site_url}/og/home.png" if site_url else "../og/home.png"
    cat_feed_abs = f"{site_url}/feed/{cat_key}.xml" if site_url else f"../feed/{cat_key}.xml"
    cat_feed_rel = f"../feed/{cat_key}.xml"
    analytics_head = _build_analytics_head(m)

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


# ---------------------------------------------------------------------------
# generate_stats_page
# ---------------------------------------------------------------------------

def generate_stats_page(episodes: list[dict], monetization: dict, base_url: str) -> str:
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

    cat_counts: dict[str, int] = {}
    for ep in episodes:
        k = (_THEMES.get(ep["theme"]) or {}).get("category") or "其他"
        cat_counts[k] = cat_counts.get(k, 0) + 1

    configured_themes = set((_THEMES or {}).keys())
    produced_themes = {ep["theme"] for ep in episodes}
    missing_themes = sorted(configured_themes - produced_themes)

    theme_counts: dict[str, int] = {}
    for ep in episodes:
        theme_counts[ep["theme"]] = theme_counts.get(ep["theme"], 0) + 1
    theme_top = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)

    latest = max((e["timestamp"] for e in episodes), default=None)
    latest_str = latest.strftime("%Y-%m-%d %H:%M") if latest else "—"
    days_since = (_dt.datetime.now() - latest).days if latest else None

    weeks: dict[str, int] = {}
    if episodes:
        for ep in episodes:
            iso_year, iso_week, _ = ep["timestamp"].isocalendar()
            key = f"{iso_year}-W{iso_week:02d}"
            weeks[key] = weeks.get(key, 0) + 1
    recent_weeks = sorted(weeks.items())[-8:]

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

    max_theme = theme_top[0][1] if theme_top else 1
    theme_rows: list[str] = []
    for name, n in theme_top[:10]:
        width_pct = (n / max_theme) * 100 if max_theme else 0
        theme_rows.append(
            f'<div class="row"><span class="row-label"><a href="theme/{_esc(name)}.html">{_esc(name)}</a></span>'
            f'<div class="bar-track"><div class="bar bar-theme" style="width:{width_pct:.1f}%">{n}</div></div></div>'
        )

    max_week = max((n for _, n in recent_weeks), default=1) or 1
    week_rows: list[str] = []
    for label, n in recent_weeks:
        h_pct = (n / max_week) * 100
        week_rows.append(
            f'<div class="week-col"><div class="week-bar" style="height:{h_pct:.0f}%" title="{n} 期"></div>'
            f'<div class="week-label">{_esc(label[-3:])}</div></div>'
        )

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
    {_pwa_head("")}
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
          <a href="privacy.html">隐私</a>
          <a href="terms.html">条款</a>
          <a href="episodes.json">episodes.json</a>
          <a href="feed.xml">RSS</a>
        </div>
      </div>
    </body>
    </html>
    """)
