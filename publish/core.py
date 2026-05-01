#!/usr/bin/env python3
"""Core constants, episode scanning, audio deployment, and small helpers.

Everything here is dependency-light (stdlib only, plus optional covers / audio_tags / config)
so other modules can import freely.
"""
import datetime
import html as html_mod
import json
import os
import re
import shutil
import struct
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

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = ROOT_DIR / "outputs"
SITE_DIR = ROOT_DIR / "site"
MONETIZATION_PATH = ROOT_DIR / "monetization.json"
MONETIZATION_EXAMPLE_PATH = ROOT_DIR / "monetization.example.json"

PODCAST_TITLE = "助眠电台 · Bedtime Story Agent"
PODCAST_DESC = "全自动 AI 助眠音频——从文字到可发布的成品，每一期都是独一无二的深度睡眠旅程。"
PODCAST_AUTHOR = "Bedtime Story Agent"
PODCAST_LANG = "zh-cn"
PODCAST_CATEGORY = "Health &amp; Fitness"


# ---------------------------------------------------------------------------
# Monetization config
# ---------------------------------------------------------------------------

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

    # Deploy per-episode scene images (AI-generated via Pollinations, optional)
    scenes_out = site_dir / "scenes"
    scenes_deployed = 0
    for ep in episodes:
        src_scene = Path(ep["audio_abs"]).parent / "scene_1.png"
        if not src_scene.is_file():
            continue
        scenes_out.mkdir(parents=True, exist_ok=True)
        dest_scene = scenes_out / f"{ep['folder']}.png"
        if not dest_scene.is_file() or dest_scene.stat().st_mtime < src_scene.stat().st_mtime:
            shutil.copy2(src_scene, dest_scene)
            scenes_deployed += 1
        ep["site_scene"] = f"scenes/{ep['folder']}.png"
    if scenes_deployed:
        print(f"[OK] 场景图 × {scenes_deployed} → {scenes_out}")


# ---------------------------------------------------------------------------
# Audio path resolution
# ---------------------------------------------------------------------------

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
# Small helpers
# ---------------------------------------------------------------------------

def _fmt_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _esc(s: str) -> str:
    return html_mod.escape(s or "", quote=True)


def _episode_slug(ep: dict) -> str:
    return ep["folder"]


def _episode_href(ep: dict) -> str:
    """Link path from site/index.html to the episode page."""
    return f"episodes/{_episode_slug(ep)}.html"


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
        scored.append((-overlap, time_delta, ep))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored[:k]]


# ---------------------------------------------------------------------------
# Chapter / share-text extraction
# ---------------------------------------------------------------------------

_SRT_BLOCK_RE = re.compile(
    r"(\d+):(\d+):(\d+)[,\.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,\.](\d+)"
)

_PHASE_RE = re.compile(r"\[阶段[:：]\s*([^\]]+)\]")
_PAUSE_RE = re.compile(r"\[停顿[^\]]*\]")
_CUE_RE = re.compile(r"\[环境音[:：]\s*([^\]]+)\]")
_STRIP_RE = re.compile(r"\[[^\]]+\]")


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


def build_share_texts(ep: dict, theme_cfg: dict | None = None) -> dict[str, str]:
    """Build platform-tailored share text for one episode.

    Same logic used for both episode-page inline JS and offline social-post
    export (site/share/{folder}.json). Keeping this in one place prevents
    the two copies drifting apart."""
    theme_cfg = theme_cfg or {}
    pain_for_share = (theme_cfg.get("pain_point", "") or "").strip()
    tech_for_share = (theme_cfg.get("technique", "") or "").split("：")[0].strip() or "心理学助眠技术"
    return {
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
