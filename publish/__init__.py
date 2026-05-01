"""publish/ package -- backward-compatible re-exports.

All public symbols from submodules are re-exported here so that
``from publish import generate_html, scan_episodes, generate_rss``
continues to work after the monolith was split.
"""

# core
from .core import (
    MONETIZATION_EXAMPLE_PATH,
    MONETIZATION_PATH,
    OUTPUTS_DIR,
    PODCAST_AUTHOR,
    PODCAST_CATEGORY,
    PODCAST_DESC,
    PODCAST_LANG,
    PODCAST_TITLE,
    ROOT_DIR,
    SITE_DIR,
    _THEME_CATEGORIES,
    _THEMES,
    _audio_tags,
    _covers,
    _breadcrumb_jsonld,
    _episode_href,
    _episode_slug,
    _esc,
    _estimate_mp3_duration,
    _fmt_duration,
    _related_episodes,
    build_share_texts,
    deploy_audio,
    extract_chapters,
    load_monetization,
    resolve_html_audio,
    resolve_rss_audio,
    scan_episodes,
)

# rss
from .rss import generate_rss

# pwa
from .pwa import (
    _pwa_head,
    generate_chapters_json,
    generate_episodes_manifest,
    generate_pwa_manifest,
    generate_service_worker,
)

# pages_common -- shared constants + newsletter form
from .pages_common import (
    _NEWSLETTER_CSS,
    _NEWSLETTER_JS,
    _build_newsletter_form,
    _build_placeholder_html,
)

# pages -- shared helpers + homepage
from .pages import (
    _build_analytics_head,
    _build_head_meta,
    _build_subscribe_html,
    _build_support_html,
    generate_html,
    render_script_html,
    render_script_plaintext,
)

# pages_episode
from .pages_episode import generate_episode_page

# pages_taxy
from .pages_taxy import (
    generate_category_page,
    generate_stats_page,
    generate_theme_page,
    generate_themes_hub,
)

# pages_legal
from .pages_legal import (
    _legal_page_template,
    generate_about_page,
    generate_faq_page,
    generate_privacy_page,
    generate_robots,
    generate_sitemap,
    generate_terms_page,
)
