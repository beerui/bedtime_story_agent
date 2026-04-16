#!/usr/bin/env python3
"""ID3 tag + chapter embedding for bedtime-story MP3s.

写入 ID3v2.4 基础元数据（title/artist/album/comment/genre）和章节（CHAP+CTOC），
让 Apple Podcasts / Pocket Casts / Overcast 等播客客户端能显示章节跳转。

依赖 mutagen；未安装则 `available()` 返回 False，调用方应自行跳过。

用法:
    from audio_tags import available, embed_episode_metadata
    if available():
        embed_episode_metadata(
            mp3_path="site/audio/Batch_.../episode.mp3",
            title="AI焦虑夜_数字排毒",
            artist="助眠电台",
            album="助眠电台 · Bedtime Story Agent",
            comment="本期描述...",
            chapters=[{"title": "引入", "start_sec": 0.0, "end_sec": 38.4}, ...],
        )
"""
from __future__ import annotations

from pathlib import Path

try:
    from mutagen.id3 import (
        ID3, ID3NoHeaderError,
        TIT2, TPE1, TALB, TCON, COMM, TYER,
        CHAP, CTOC, CTOCFlags,
    )
    from mutagen.mp3 import MP3
    _HAS_MUTAGEN = True
except ImportError:
    _HAS_MUTAGEN = False


def available() -> bool:
    return _HAS_MUTAGEN


def embed_episode_metadata(
    mp3_path: str | Path,
    title: str,
    artist: str = "助眠电台",
    album: str = "助眠电台 · Bedtime Story Agent",
    comment: str = "",
    genre: str = "Podcast",
    year: str = "",
    chapters: list[dict] | None = None,
) -> bool:
    """Write ID3v2.4 tags + optional CHAP chapters into the MP3.

    Returns True on success, False if mutagen missing or file unusable.
    chapters: list of {title, start_sec, end_sec} — start/end in seconds.
    """
    if not _HAS_MUTAGEN:
        return False

    path = Path(mp3_path)
    if not path.is_file():
        return False

    try:
        audio = MP3(str(path))
    except Exception:
        return False

    if audio.tags is None:
        try:
            audio.add_tags()
        except Exception:
            return False

    tags: ID3 = audio.tags  # type: ignore[assignment]

    # Clear existing CHAP/CTOC so we don't duplicate on re-runs
    for key in list(tags.keys()):
        if key.startswith("CHAP:") or key.startswith("CTOC:"):
            del tags[key]

    # Basic metadata (ID3v2.4)
    tags["TIT2"] = TIT2(encoding=3, text=title)
    tags["TPE1"] = TPE1(encoding=3, text=artist)
    tags["TALB"] = TALB(encoding=3, text=album)
    tags["TCON"] = TCON(encoding=3, text=genre)
    if year:
        tags["TYER"] = TYER(encoding=3, text=year)
    if comment:
        tags["COMM::XXX"] = COMM(encoding=3, lang="chi", desc="", text=comment)

    # Chapters (ID3v2.4 CHAP + CTOC)
    if chapters:
        child_ids: list[str] = []
        for i, ch in enumerate(chapters):
            cid = f"ch{i:03d}"
            child_ids.append(cid)
            start_ms = int(ch["start_sec"] * 1000)
            end_ms = int(ch["end_sec"] * 1000)
            chap = CHAP(
                element_id=cid,
                start_time=start_ms,
                end_time=end_ms,
                start_offset=0xFFFFFFFF,
                end_offset=0xFFFFFFFF,
                sub_frames=[TIT2(encoding=3, text=ch["title"])],
            )
            tags.add(chap)

        toc = CTOC(
            element_id="toc",
            flags=CTOCFlags.TOP_LEVEL | CTOCFlags.ORDERED,
            child_element_ids=child_ids,
            sub_frames=[TIT2(encoding=3, text="Chapters")],
        )
        tags.add(toc)

    try:
        tags.save(str(path), v2_version=4)
    except Exception:
        return False

    return True
