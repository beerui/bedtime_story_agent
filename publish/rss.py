#!/usr/bin/env python3
"""RSS 2.0 feed generation (Podcast 2.0 / Apple Podcasts compliant)."""
import uuid as _uuid
import xml.etree.ElementTree as ET

from .core import (
    PODCAST_AUTHOR,
    PODCAST_CATEGORY,
    PODCAST_DESC,
    PODCAST_LANG,
    PODCAST_TITLE,
    _THEMES,
    _THEME_CATEGORIES,
    resolve_rss_audio,
)


def generate_rss(episodes: list[dict], base_url: str,
                  category_key: str = "", category_cfg: dict | None = None,
                  monetization: dict | None = None) -> str:
    """Generate a Podcast RSS 2.0 XML feed compliant with Apple Podcasts
    Connect submission requirements (iTunes namespace).

    When category_key+category_cfg are given, produces a filtered feed covering
    only episodes whose theme belongs to that category. Channel title/description
    are customized for the category so podcast apps render distinct feeds."""
    ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"
    CONTENT = "{http://purl.org/rss/1.0/modules/content/}"
    PODCAST_NS = "{https://podcastindex.org/namespace/1.0}"
    ET.register_namespace("itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    ET.register_namespace("content", "http://purl.org/rss/1.0/modules/content/")
    ET.register_namespace("podcast", "https://podcastindex.org/namespace/1.0")

    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    m = monetization or {}
    site_url = (base_url or m.get("site_url") or "").rstrip("/")
    cover_url = f"{site_url}/podcast-cover.png" if site_url else "podcast-cover.png"
    contact_email = (((m.get("social") or {}).get("contact_email") or "").strip()
                     or "hello@bedtime.local")

    if category_key and category_cfg:
        cat_label = category_cfg.get("label", category_key)
        channel_title = f"{PODCAST_TITLE} · {cat_label}"
        channel_desc = category_cfg.get("description", PODCAST_DESC)
        channel_link = f"{site_url}/category/{category_key}.html" if site_url else "index.html"
    else:
        channel_title = PODCAST_TITLE
        channel_desc = PODCAST_DESC
        channel_link = site_url or "https://example.com"

    ET.SubElement(channel, "title").text = channel_title
    ET.SubElement(channel, "description").text = channel_desc
    ET.SubElement(channel, "language").text = PODCAST_LANG
    ET.SubElement(channel, "link").text = channel_link

    # iTunes-namespace channel tags (Apple Podcasts required set)
    ET.SubElement(channel, f"{ITUNES}author").text = PODCAST_AUTHOR
    ET.SubElement(channel, f"{ITUNES}summary").text = channel_desc
    ET.SubElement(channel, f"{ITUNES}explicit").text = "no"
    ET.SubElement(channel, f"{ITUNES}type").text = "episodic"

    img = ET.SubElement(channel, f"{ITUNES}image")
    img.set("href", cover_url)

    owner = ET.SubElement(channel, f"{ITUNES}owner")
    ET.SubElement(owner, f"{ITUNES}name").text = PODCAST_AUTHOR
    ET.SubElement(owner, f"{ITUNES}email").text = contact_email

    # Primary category + sub-category for health/wellness podcasts
    cat_elem = ET.SubElement(channel, f"{ITUNES}category")
    cat_elem.set("text", "Health & Fitness")
    sub = ET.SubElement(cat_elem, f"{ITUNES}category")
    sub.set("text", "Mental Health")

    # Atom-style self link for feedburner validators
    atom_link = ET.SubElement(channel, "{http://www.w3.org/2005/Atom}link")
    feed_self = f"{site_url}/feed.xml" if site_url else "feed.xml"
    if category_key:
        feed_self = f"{site_url}/feed/{category_key}.xml" if site_url else f"feed/{category_key}.xml"
    atom_link.set("href", feed_self)
    atom_link.set("rel", "self")
    atom_link.set("type", "application/rss+xml")

    # Podcast 2.0 namespace: stable show-level GUID derived from site URL.
    if site_url:
        show_guid = str(_uuid.uuid5(_uuid.NAMESPACE_URL, f"{site_url}/{category_key or ''}"))
        ET.SubElement(channel, f"{PODCAST_NS}guid").text = show_guid

    # Filter episodes if category_key given
    if category_key:
        episodes = [
            e for e in episodes
            if (_THEMES.get(e.get("theme")) or {}).get("category") == category_key
        ]

    for idx, ep in enumerate(episodes):
        item = ET.SubElement(channel, "item")
        ET.SubElement(item, "title").text = ep["title"]
        ET.SubElement(item, "description").text = ep["description"]
        ET.SubElement(item, "pubDate").text = ep["pub_date"]

        audio_url = resolve_rss_audio(ep, base_url)
        enc = ET.SubElement(item, "enclosure")
        enc.set("url", audio_url)
        enc.set("length", str(ep["audio_size"]))
        enc.set("type", "audio/mpeg")

        dur = ET.SubElement(item, f"{ITUNES}duration")
        mm, ss = divmod(ep["duration"], 60)
        dur.text = f"{mm}:{ss:02d}"

        # iTunes-namespace per-episode metadata
        ET.SubElement(item, f"{ITUNES}summary").text = ep["description"]
        ET.SubElement(item, f"{ITUNES}author").text = PODCAST_AUTHOR
        ET.SubElement(item, f"{ITUNES}episodeType").text = "full"
        ET.SubElement(item, f"{ITUNES}explicit").text = "no"
        ep_square = f"{site_url}/covers/{ep['folder']}.png" if site_url else cover_url
        ep_img = ET.SubElement(item, f"{ITUNES}image")
        ep_img.set("href", ep_square)

        # Podcast 2.0: transcript link
        if site_url:
            transcript_url = f"{site_url}/episodes/{ep['folder']}.txt"
            tr = ET.SubElement(item, f"{PODCAST_NS}transcript")
            tr.set("url", transcript_url)
            tr.set("type", "text/plain")
            tr.set("language", PODCAST_LANG)

            # Podcast 2.0: JSON chapters link
            chapters_url = f"{site_url}/episodes/{ep['folder']}.chapters.json"
            ch = ET.SubElement(item, f"{PODCAST_NS}chapters")
            ch.set("url", chapters_url)
            ch.set("type", "application/json+chapters")

        ET.SubElement(item, "guid", isPermaLink="false").text = ep["folder"]

    ET.indent(rss, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(rss, encoding="unicode")
