#!/usr/bin/env python3
"""批量回填现有 outputs/ 下每期的 chapter_titles.json。

调用 engine._generate_chapter_titles(story_text, theme_name) 为已有剧本
补生成 3 个具体章节标题（替代通用的 引入/深入/尾声）。已存在文件默认跳过。

用法:
    python3 backfill_chapter_titles.py          # 所有缺失的期
    python3 backfill_chapter_titles.py --force  # 强制覆盖已有的
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--force", action="store_true", help="覆盖已有 chapter_titles.json")
    parser.add_argument("--dry-run", action="store_true", help="仅列出将处理的文件夹，不调用 LLM")
    args = parser.parse_args()

    outputs = Path(__file__).parent / "outputs"
    if not outputs.is_dir():
        print("outputs/ 不存在")
        return 1

    try:
        import engine
    except Exception as e:
        print(f"engine 导入失败（需要 DASHSCOPE_API_KEY 在 .env）: {e}")
        return 1

    candidates: list[tuple[Path, str]] = []
    for folder in sorted(outputs.iterdir()):
        if not folder.is_dir() or not folder.name.startswith("Batch_"):
            continue
        story_path = folder / "story_draft.txt"
        if not story_path.is_file():
            continue
        titles_path = folder / "chapter_titles.json"
        if titles_path.is_file() and not args.force:
            continue
        # extract theme from folder name: Batch_YYYYMMDD_HHMMSS_主题[_EPN]
        parts = folder.name.split("_", 3)
        theme = parts[3] if len(parts) >= 4 else folder.name
        # Strip possible episode suffix like _EP2
        if theme.rsplit("_EP", 1)[0] and theme.rsplit("_EP", 1)[-1].isdigit():
            theme = theme.rsplit("_EP", 1)[0]
        candidates.append((folder, theme))

    if not candidates:
        print("没有需要回填的期。")
        return 0

    print(f"待处理 {len(candidates)} 个 Batch_ 文件夹：")
    for folder, theme in candidates:
        print(f"  {folder.name}  (theme={theme})")

    if args.dry_run:
        print("\n[dry-run] 未调用 LLM")
        return 0

    ok_count = 0
    fail_count = 0
    for folder, theme in candidates:
        try:
            story_text = (folder / "story_draft.txt").read_text(encoding="utf-8")
            titles = engine._generate_chapter_titles(story_text, theme)
            if not titles:
                print(f"  [skip] {folder.name}  (LLM 返回为空或解析失败)")
                fail_count += 1
                continue
            (folder / "chapter_titles.json").write_text(
                json.dumps(titles, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            labels = " / ".join(titles.values())
            print(f"  [ok]   {folder.name}  {labels}")
            ok_count += 1
        except Exception as e:
            print(f"  [fail] {folder.name}  {e}")
            fail_count += 1

    print(f"\n完成：{ok_count} 成功，{fail_count} 失败")
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
