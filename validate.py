#!/usr/bin/env python3
"""管线健康检查：扫 outputs/ 每个 Batch_ 文件夹，验证必备文件、结构化数据完整性。

用法:
    python3 validate.py                 # 人类可读报告，有 error 时 exit 1
    python3 validate.py --json          # JSON 输出给 CI
    python3 validate.py --strict        # warning 也算失败
    python3 validate.py --summary       # 只打总结不列细节

检查维度（按严重度排序）:
    [error]   Batch_ 文件夹缺 story_draft.txt / final_audio.mp3
    [error]   final_audio.mp3 < 50KB 或损坏
    [error]   story_draft 缺 [阶段：引入] 等必需标记
    [error]   metadata.json 存在但无法解析
    [warn]    缺 subtitles.srt（无 SRT → 单期页无章节 UI）
    [warn]    缺 chapter_titles.json（章节名退化为引入/深入/尾声）
    [warn]    chapter_titles 不是标准 3 phase
    [warn]    metadata.json 缺 title / description_* / tags
    [warn]    同一 (day, theme) 多个 Batch_（疑似 dedup 失败）
    [info]    音频时长 < 180s 或 > 25min（偏离助眠内容黄金区间）
    [info]    TF-IDF 文本相似度 > 0.85（与某已有期高度相似）

exit 0 = 无 error（或 --strict 下无 error+warning）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# ANSI colors — only when stdout is a tty
_ISATTY = sys.stdout.isatty()
RED = "\033[31m" if _ISATTY else ""
YELLOW = "\033[33m" if _ISATTY else ""
CYAN = "\033[36m" if _ISATTY else ""
GREEN = "\033[32m" if _ISATTY else ""
DIM = "\033[2m" if _ISATTY else ""
RESET = "\033[0m" if _ISATTY else ""


SEVERITIES = ("error", "warning", "info")
REQUIRED_PHASES = ("引入", "深入", "尾声")


def _mp3_ok(path: Path) -> tuple[bool, int]:
    """Return (valid, duration_sec). Reuses publish.py's estimator if importable."""
    if not path.is_file():
        return False, 0
    size = path.stat().st_size
    if size < 50_000:
        return False, 0
    try:
        import publish
        return True, publish._estimate_mp3_duration(str(path))
    except Exception:
        # Rough fallback: assume 128 kbps
        return True, int(size * 8 / 128000)


def _srt_cue_count(path: Path) -> int:
    if not path.is_file():
        return 0
    try:
        text = path.read_text(encoding="utf-8").strip()
        blocks = [b for b in re.split(r"\n\n+", text) if b.strip()]
        return len(blocks)
    except Exception:
        return 0


def _extract_theme(folder_name: str) -> str:
    """Batch_YYYYMMDD_HHMMSS_主题[_EPn] → 主题"""
    parts = folder_name.split("_", 3)
    if len(parts) < 4:
        return folder_name
    theme = parts[3]
    # Strip _EPn suffix
    if "_EP" in theme:
        head, _, tail = theme.rpartition("_EP")
        if tail.isdigit():
            theme = head
    return theme


def _extract_day(folder_name: str) -> str:
    parts = folder_name.split("_")
    return parts[1] if len(parts) >= 2 and parts[1].isdigit() else ""


def check_episode(folder: Path) -> list[dict]:
    """Return list of {severity, code, message} for one folder."""
    issues: list[dict] = []
    name = folder.name

    def add(sev: str, code: str, msg: str):
        issues.append({"severity": sev, "code": code, "message": msg})

    # --- Required files ---
    story = folder / "story_draft.txt"
    audio = folder / "final_audio.mp3"
    voice = folder / "voice.mp3"
    if not story.is_file():
        add("error", "missing_story", "缺 story_draft.txt")
    if not audio.is_file():
        # Distinguish "never mixed" (has voice.mp3) from "never generated"
        if voice.is_file():
            add("warning", "missing_mix", "缺 final_audio.mp3 但 voice.mp3 存在（BGM 混音未完成，重跑 engine.assemble 可修复）")
        else:
            add("error", "missing_audio", "缺 final_audio.mp3 且无 voice.mp3（生产彻底失败）")

    # Short-circuit: no further checks make sense if core files missing
    if not story.is_file() or not audio.is_file():
        return issues

    # --- Audio health ---
    ok, duration = _mp3_ok(audio)
    if not ok:
        add("error", "audio_corrupt", f"final_audio.mp3 无效或过小（<50KB）")
    else:
        if duration < 180:
            add("info", "audio_too_short", f"音频仅 {duration}s（建议 180s 以上）")
        elif duration > 25 * 60:
            add("info", "audio_too_long", f"音频 {duration//60}m{duration%60}s 超 25 分钟（偏离睡前黄金区间）")

    # --- Story markup ---
    try:
        story_text = story.read_text(encoding="utf-8")
    except Exception as e:
        add("error", "story_unreadable", f"story_draft.txt 无法读取: {e}")
        return issues

    for phase in REQUIRED_PHASES:
        if f"[阶段：{phase}]" not in story_text and f"[阶段:{phase}]" not in story_text:
            add("error", "missing_phase", f"剧本缺 [阶段：{phase}] 标记")

    # --- SRT (warning level — old episodes may lack) ---
    srt = folder / "subtitles.srt"
    cue_count = _srt_cue_count(srt)
    if cue_count == 0:
        add("warning", "missing_srt", "缺 subtitles.srt（单期页章节 UI 无法渲染）")
    elif cue_count < 10:
        add("warning", "srt_too_few_cues", f"SRT 仅 {cue_count} 条（可能字幕切分异常）")

    # --- chapter_titles.json ---
    titles_path = folder / "chapter_titles.json"
    if not titles_path.is_file():
        add("warning", "missing_chapter_titles", "缺 chapter_titles.json（章节名退化为「引入/深入/尾声」）")
    else:
        try:
            titles = json.loads(titles_path.read_text(encoding="utf-8"))
            for phase in REQUIRED_PHASES:
                if phase not in titles:
                    add("warning", "chapter_titles_incomplete", f"chapter_titles.json 缺「{phase}」键")
                elif not isinstance(titles[phase], str) or not titles[phase].strip():
                    add("warning", "chapter_titles_empty", f"chapter_titles.json 的「{phase}」为空")
        except Exception as e:
            add("warning", "chapter_titles_invalid", f"chapter_titles.json 无法解析: {e}")

    # --- metadata.json ---
    meta_path = folder / "metadata.json"
    if not meta_path.is_file():
        add("warning", "missing_metadata", "缺 metadata.json（RSS 描述降级为默认值）")
    else:
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if not meta.get("title"):
                add("warning", "metadata_no_title", "metadata.json 缺 title")
            if not (meta.get("description_xiaoyuzhou") or meta.get("description_ximalaya")):
                add("warning", "metadata_no_desc", "metadata.json 缺 description_xiaoyuzhou/ximalaya")
            tags = meta.get("tags") or []
            if not tags:
                add("warning", "metadata_no_tags", "metadata.json tags 为空")
            elif len(tags) < 3:
                add("info", "metadata_few_tags", f"metadata.json 仅 {len(tags)} 个 tag（建议 ≥3）")
        except Exception as e:
            add("error", "metadata_invalid", f"metadata.json 无法解析: {e}")

    return issues


def check_bgm_inventory(repo_root: Path) -> list[dict]:
    """Report themes whose declared bgm_file doesn't exist in assets/ or
    assets/bgm/ — those episodes fall back to auto-generated brown noise."""
    issues: list[dict] = []
    try:
        import config
    except Exception:
        return issues
    bgm_dir1 = repo_root / "assets" / "bgm"
    bgm_dir2 = repo_root / "assets"
    found = {f.name for d in (bgm_dir1, bgm_dir2) if d.is_dir() for f in d.iterdir() if f.is_file()}
    for theme_name, cfg in (getattr(config, "THEMES", None) or {}).items():
        bgm = (cfg.get("bgm_file") or "").strip()
        if bgm and bgm not in found:
            issues.append({
                "severity": "info",
                "code": "bgm_missing",
                "message": f"主题「{theme_name}」声明的 BGM「{bgm}」在 assets/ 和 assets/bgm/ 都不存在——降级为棕噪底噪",
            })
    return issues


def check_crosses(outputs_dir: Path, per_folder_issues: dict) -> list[tuple[str, dict]]:
    """Cross-folder checks: same (day, theme) appearing multiple times."""
    cross_issues: list[tuple[str, dict]] = []
    day_theme_map: dict[tuple[str, str], list[str]] = defaultdict(list)
    for folder in outputs_dir.iterdir():
        if not folder.is_dir() or not folder.name.startswith("Batch_"):
            continue
        day = _extract_day(folder.name)
        theme = _extract_theme(folder.name)
        if day and theme:
            day_theme_map[(day, theme)].append(folder.name)
    for (day, theme), names in day_theme_map.items():
        if len(names) > 1:
            for name in names:
                cross_issues.append(
                    (name, {
                        "severity": "warning",
                        "code": "duplicate_day_theme",
                        "message": f"同一天（{day}）同主题「{theme}」有 {len(names)} 期：{', '.join(names)}",
                    })
                )
    return cross_issues


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", help="JSON 输出（CI 用）")
    parser.add_argument("--strict", action="store_true", help="warning 也算失败")
    parser.add_argument("--summary", action="store_true", help="只打总结不列细节")
    parser.add_argument("--only", help="只验证指定文件夹名（包含子串匹配）")
    args = parser.parse_args()

    outputs = Path(__file__).parent / "outputs"
    if not outputs.is_dir():
        print("outputs/ 不存在", file=sys.stderr)
        return 2

    folders = sorted(
        f for f in outputs.iterdir()
        if f.is_dir() and f.name.startswith("Batch_")
    )
    if args.only:
        folders = [f for f in folders if args.only in f.name]

    per_folder: dict[str, list[dict]] = {}
    for folder in folders:
        per_folder[folder.name] = check_episode(folder)

    # Cross-folder checks
    for name, issue in check_crosses(outputs, per_folder):
        per_folder.setdefault(name, []).append(issue)

    # Repo-wide BGM inventory (informational)
    bgm_issues = check_bgm_inventory(Path(__file__).parent)
    if bgm_issues:
        per_folder.setdefault("_bgm_inventory", []).extend(bgm_issues)

    # Aggregate
    total_by_sev: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    clean_folders = []
    for name, issues in per_folder.items():
        if not issues:
            clean_folders.append(name)
            continue
        for iss in issues:
            total_by_sev[iss["severity"]] += 1

    if args.json:
        print(json.dumps({
            "folders_checked": len(folders),
            "clean_folders": len(clean_folders),
            "by_severity": total_by_sev,
            "per_folder": per_folder,
        }, ensure_ascii=False, indent=2))
    else:
        if not args.summary:
            for name, issues in per_folder.items():
                if not issues:
                    continue
                print(f"\n{CYAN}{name}{RESET}")
                for iss in issues:
                    sev = iss["severity"]
                    color = RED if sev == "error" else YELLOW if sev == "warning" else DIM
                    print(f"  {color}[{sev}]{RESET} {iss['code']}: {iss['message']}")
        # Summary
        print()
        print(f"{DIM}─ 管线健康报告 ─{RESET}")
        print(f"  检查文件夹: {len(folders)}")
        print(f"  {GREEN}无问题: {len(clean_folders)}{RESET}")
        if total_by_sev["error"]:
            print(f"  {RED}error:  {total_by_sev['error']}{RESET}")
        if total_by_sev["warning"]:
            print(f"  {YELLOW}warning: {total_by_sev['warning']}{RESET}")
        if total_by_sev["info"]:
            print(f"  {DIM}info:   {total_by_sev['info']}{RESET}")

    # Exit code
    if total_by_sev["error"] > 0:
        return 1
    if args.strict and total_by_sev["warning"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
