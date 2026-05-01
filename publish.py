#!/usr/bin/env python3
"""Thin entry point -- delegates to publish/ package.

Keeps only main() + CLI arg parsing. All generation logic lives in publish/{core, rss, pages, pwa}.py.

用法:
    python3 publish.py                      # 生成到 site/
    python3 publish.py --serve              # 生成 + 启动本地服务器 + 打开浏览器
    python3 publish.py --base-url URL       # 设置音频 URL 前缀（用于公网部署）
"""
import argparse
import http.server
import json
import os
import threading
import webbrowser

from publish import (
    MONETIZATION_EXAMPLE_PATH,
    MONETIZATION_PATH,
    OUTPUTS_DIR,
    SITE_DIR,
    _THEME_CATEGORIES,
    _THEMES,
    _build_placeholder_html,
    _covers,
    _episode_slug,
    _related_episodes,
    build_share_texts,
    deploy_audio,
    generate_about_page,
    generate_category_page,
    generate_chapters_json,
    generate_episode_page,
    generate_episodes_manifest,
    generate_faq_page,
    generate_html,
    generate_privacy_page,
    generate_pwa_manifest,
    generate_robots,
    generate_rss,
    generate_service_worker,
    generate_sitemap,
    generate_stats_page,
    generate_terms_page,
    generate_theme_page,
    generate_themes_hub,
    load_monetization,
    render_script_plaintext,
    scan_episodes,
)


def main():
    parser = argparse.ArgumentParser(description="生成播客站点（播放器 + RSS 订阅源）")
    parser.add_argument("--base-url", default="", help="音频 URL 前缀（公网部署时使用）")
    parser.add_argument("--serve", action="store_true", help="生成后启动本地 HTTP 服务器并打开浏览器")
    parser.add_argument("--port", type=int, default=8888, help="本地服务器端口（默认 8888）")
    parser.add_argument("--copy-audio", action="store_true",
                        help="把 outputs/ 中的音频复制到 site/audio/，使站点可独立部署（GitHub Pages / Vercel）")
    args = parser.parse_args()

    episodes = scan_episodes(OUTPUTS_DIR)
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
        next_ep = episodes[i - 1] if i - 1 >= 0 else None
        prev_ep = episodes[i + 1] if i + 1 < len(episodes) else None
        related = _related_episodes(ep, episodes, k=3)
        page = generate_episode_page(
            ep, monetization, args.base_url, len(episodes),
            prev_ep=prev_ep, next_ep=next_ep, related=related,
        )
        (episodes_dir / f"{_episode_slug(ep)}.html").write_text(page, encoding="utf-8")
        plain = render_script_plaintext(ep.get("draft_full", ""), ep.get("chapter_titles"))
        if plain:
            (episodes_dir / f"{_episode_slug(ep)}.txt").write_text(plain, encoding="utf-8")
        ch_json = generate_chapters_json(ep)
        if ch_json:
            (episodes_dir / f"{_episode_slug(ep)}.chapters.json").write_text(ch_json, encoding="utf-8")
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
                continue
            if _covers.generate_episode_cover(ep, out):
                generated += 1
        print(f"[OK] OG 封面 → {og_dir}（新生成 {generated} 张，共 {len(episodes) + 1} 张）")
        pc_path = SITE_DIR / "podcast-cover.png"
        if not pc_path.is_file():
            tagline = (monetization or {}).get("brand_tagline") or "每晚 10 分钟 · AI 助眠"
            if _covers.generate_podcast_cover(pc_path, tagline=tagline):
                print(f"[OK] 播客方形封面（1400x1400） → {pc_path}")
        sq_dir = SITE_DIR / "covers"
        sq_dir.mkdir(exist_ok=True)
        sq_generated = 0
        for ep in episodes:
            sq_out = sq_dir / f"{ep['folder']}.png"
            if sq_out.is_file():
                continue
            theme_cfg = (_THEMES or {}).get(ep.get("theme")) or {}
            if _covers.generate_episode_square_cover(
                ep, sq_out, pain_point=theme_cfg.get("pain_point", "")
            ):
                sq_generated += 1
        if sq_generated:
            print(f"[OK] 每期方形封面 × {sq_generated} → {sq_dir}（1400x1400）")
    else:
        print("[skip] OG 封面未生成（Pillow 未安装；pip install Pillow 启用）")

    # generate sitemap.xml + robots.txt
    (SITE_DIR / "sitemap.xml").write_text(generate_sitemap(episodes, args.base_url), encoding="utf-8")
    (SITE_DIR / "robots.txt").write_text(generate_robots(args.base_url), encoding="utf-8")
    print(f"[OK] sitemap.xml + robots.txt → {SITE_DIR}")

    # generate About page
    (SITE_DIR / "about.html").write_text(
        generate_about_page(monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] 关于页 → {SITE_DIR / 'about.html'}")

    # generate FAQ page
    (SITE_DIR / "faq.html").write_text(
        generate_faq_page(monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] FAQ 页 → {SITE_DIR / 'faq.html'}")

    # generate Privacy + Terms pages
    (SITE_DIR / "privacy.html").write_text(
        generate_privacy_page(monetization, args.base_url), encoding="utf-8"
    )
    (SITE_DIR / "terms.html").write_text(
        generate_terms_page(monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] 隐私+条款页 → {SITE_DIR / 'privacy.html'} / terms.html")

    # generate stats page
    (SITE_DIR / "stats.html").write_text(
        generate_stats_page(episodes, monetization, args.base_url), encoding="utf-8"
    )
    print(f"[OK] 数据页 → {SITE_DIR / 'stats.html'}")

    # generate per-category landing pages
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

    # generate per-theme landing pages
    theme_dir = SITE_DIR / "theme"
    theme_dir.mkdir(exist_ok=True)
    theme_generated = 0
    for theme_name, theme_cfg in (_THEMES or {}).items():
        if not theme_cfg.get("category"):
            continue
        page = generate_theme_page(theme_name, theme_cfg, episodes, monetization, args.base_url)
        (theme_dir / f"{theme_name}.html").write_text(page, encoding="utf-8")
        theme_generated += 1
    if theme_generated:
        print(f"[OK] 主题页 × {theme_generated} → {theme_dir}")

    # themes taxonomy hub
    if _THEMES and _THEME_CATEGORIES:
        (SITE_DIR / "themes.html").write_text(
            generate_themes_hub(monetization, args.base_url), encoding="utf-8"
        )
        print(f"[OK] 主题总览 → {SITE_DIR / 'themes.html'}")

    # generate RSS feed
    rss = generate_rss(episodes, args.base_url, monetization=monetization)
    rss_path = SITE_DIR / "feed.xml"
    rss_path.write_text(rss, encoding="utf-8")
    print(f"[OK] RSS 订阅源 → {rss_path}")

    # generate per-category RSS feeds
    if used_cats and _THEME_CATEGORIES:
        feed_dir = SITE_DIR / "feed"
        feed_dir.mkdir(exist_ok=True)
        feeds_written = 0
        for cat_key in used_cats:
            cat_cfg = _THEME_CATEGORIES.get(cat_key)
            if not cat_cfg:
                continue
            cat_rss = generate_rss(episodes, args.base_url, cat_key, cat_cfg, monetization=monetization)
            (feed_dir / f"{cat_key}.xml").write_text(cat_rss, encoding="utf-8")
            feeds_written += 1
        if feeds_written:
            print(f"[OK] 分类 RSS × {feeds_written} → {feed_dir}")

    # machine-readable manifest
    (SITE_DIR / "episodes.json").write_text(
        generate_episodes_manifest(episodes, args.base_url), encoding="utf-8"
    )
    print(f"[OK] episodes.json → {SITE_DIR / 'episodes.json'}")

    # Social posts export
    share_dir = SITE_DIR / "share"
    share_dir.mkdir(exist_ok=True)
    all_posts = {"x": [], "weibo": [], "xhs": [], "wechat": []}
    for ep in episodes:
        theme_cfg = (_THEMES or {}).get(ep["theme"]) or {}
        texts = build_share_texts(ep, theme_cfg)
        ep_url = f"{args.base_url.rstrip('/')}/episodes/{ep['folder']}.html" if args.base_url else f"episodes/{ep['folder']}.html"
        per_ep = {
            platform: {"text": t, "url": ep_url}
            for platform, t in texts.items()
        }
        (share_dir / f"{ep['folder']}.json").write_text(
            json.dumps({"episode": ep["folder"], "title": ep["title"], "posts": per_ep},
                       ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        for platform, t in texts.items():
            all_posts[platform].append({
                "episode": ep["folder"],
                "title": ep["title"],
                "published_at": ep["timestamp"].strftime("%Y-%m-%d"),
                "text": t,
                "url": ep_url,
            })
    (share_dir / "all-posts.json").write_text(
        json.dumps(all_posts, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[OK] 社交文案 × {len(episodes)} → {share_dir}（{sum(len(v) for v in all_posts.values())} 条 × 4 平台）")

    # PWA: manifest + service worker + icons
    (SITE_DIR / "manifest.webmanifest").write_text(
        generate_pwa_manifest(args.base_url), encoding="utf-8"
    )
    (SITE_DIR / "sw.js").write_text(generate_service_worker(), encoding="utf-8")
    if _covers and _covers.available():
        icons_dir = SITE_DIR / "icons"
        icons_dir.mkdir(exist_ok=True)
        if not (icons_dir / "icon-192.png").is_file():
            _covers.generate_pwa_icon(icons_dir / "icon-192.png", size=192)
        if not (icons_dir / "icon-512.png").is_file():
            _covers.generate_pwa_icon(icons_dir / "icon-512.png", size=512)
        if not (icons_dir / "icon-maskable-512.png").is_file():
            _covers.generate_pwa_icon(icons_dir / "icon-maskable-512.png", size=512, maskable=True)
        print(f"[OK] PWA manifest + sw.js + 3 icons → {SITE_DIR}")
    else:
        print(f"[OK] PWA manifest + sw.js（图标跳过：Pillow 未装）→ {SITE_DIR}")

    print(f"\n共 {len(episodes)} 期节目已发布。")

    if args.serve:
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


if __name__ == "__main__":
    main()
