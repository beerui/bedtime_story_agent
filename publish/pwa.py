#!/usr/bin/env python3
"""PWA manifest, service worker, chapter JSON, and episode manifest generation."""
import json

from .core import (
    PODCAST_DESC,
    PODCAST_LANG,
    PODCAST_TITLE,
    _episode_slug,
    extract_chapters,
    _THEMES,
    _THEME_CATEGORIES,
)


def _pwa_head(rel_prefix: str = "") -> str:
    """Return HTML snippet to place in <head> for PWA support.
    rel_prefix: '' for root-level pages, '../' for episodes/theme/category/."""
    p = rel_prefix
    return (
        f'<link rel="manifest" href="{p}manifest.webmanifest">'
        f'<meta name="theme-color" content="#7c6ff7">'
        f'<meta name="apple-mobile-web-app-capable" content="yes">'
        f'<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">'
        f'<meta name="apple-mobile-web-app-title" content="助眠电台">'
        f'<link rel="apple-touch-icon" href="{p}icons/icon-192.png">'
    )


def generate_pwa_manifest(base_url: str) -> str:
    """Generate manifest.webmanifest for PWA installability (iOS/Android home-screen)."""
    base = (base_url or "").rstrip("/")
    manifest = {
        "name": PODCAST_TITLE,
        "short_name": "助眠电台",
        "description": PODCAST_DESC,
        "start_url": "./",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#06061a",
        "theme_color": "#7c6ff7",
        "lang": "zh-CN",
        "icons": [
            {
                "src": "icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any",
            },
            {
                "src": "icons/icon-maskable-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "maskable",
            },
        ],
        "categories": ["health", "lifestyle", "entertainment"],
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2)


def generate_service_worker() -> str:
    """Service worker: caches app shell for offline-first experience."""
    return """// Service worker for 助眠电台 · offline app-shell caching
const CACHE_VERSION = 'v1';
const CACHE_NAME = `bedtime-${CACHE_VERSION}`;
const APP_SHELL = [
  './',
  'index.html',
  'about.html',
  'faq.html',
  'themes.html',
  'stats.html',
  'icons/icon-192.png',
  'icons/icon-512.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return Promise.allSettled(APP_SHELL.map(u => cache.add(u)));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (/\\.(mp3|wav|ogg|mp4|m4a|webm)$/i.test(url.pathname)) return;
  if (url.origin !== location.origin) return;

  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(req);
      const networkPromise = fetch(req).then((res) => {
        if (res.ok && res.type === 'basic') {
          cache.put(req, res.clone());
        }
        return res;
      }).catch(() => cached);
      return cached || networkPromise;
    })
  );
});
"""


def generate_chapters_json(ep: dict) -> str:
    """Generate Podcast 2.0 spec chapters.json for one episode."""
    chapters = extract_chapters(
        ep.get("draft_full", ""),
        ep.get("srt", ""),
        title_overrides=ep.get("chapter_titles") or None,
    )
    if not chapters:
        return ""
    payload = {
        "version": "1.2.0",
        "chapters": [
            {
                "startTime": round(c["start_sec"], 2),
                "title": c.get("title") or c.get("phase") or "",
            }
            for c in chapters
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def generate_episodes_manifest(episodes: list[dict], base_url: str) -> str:
    """Machine-readable episode index for 3rd-party embeds, aggregators, search APIs."""
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
