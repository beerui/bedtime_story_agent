#!/usr/bin/env python3
"""为现有的每期回填场景图（scene_1.png），供单期页作 hero 展示。

每期的 `theme.image_prompt` 通过 Pollinations.ai（免费）生成 1024x1792 竖图。
Pollinations 不需要 API key，但响应慢（单张 10-60s），且可能 503。脚本有
重试 + 串行控制避免触发频率限制。

用法:
    python3 backfill_scenes.py              # 回填所有缺场景图的期
    python3 backfill_scenes.py --dry-run    # 只列会处理的期
    python3 backfill_scenes.py --only AI焦虑  # 过滤
    python3 backfill_scenes.py --limit 5    # 只跑前 5 期
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="只列，不生成")
    parser.add_argument("--only", help="过滤文件夹名子串")
    parser.add_argument("--limit", type=int, help="最多处理 N 期")
    parser.add_argument("--sleep", type=float, default=3.0,
                        help="期间隔秒数（避免 Pollinations 频率限制）")
    args = parser.parse_args()

    try:
        import engine
    except Exception as e:
        print(f"engine 导入失败: {e}", file=sys.stderr)
        return 1

    outputs = Path(__file__).parent / "outputs"
    if not outputs.is_dir():
        print("outputs/ 不存在", file=sys.stderr)
        return 1

    candidates: list[tuple[Path, str]] = []
    for folder in sorted(outputs.iterdir()):
        if not folder.is_dir() or not folder.name.startswith("Batch_"):
            continue
        if args.only and args.only not in folder.name:
            continue
        scene = folder / "scene_1.png"
        if scene.is_file():
            continue
        parts = folder.name.split("_", 3)
        if len(parts) < 4:
            continue
        theme = parts[3]
        if theme.rsplit("_EP", 1)[0] and theme.rsplit("_EP", 1)[-1].isdigit():
            theme = theme.rsplit("_EP", 1)[0]
        if theme not in engine.THEMES:
            print(f"  [skip] {folder.name}  主题 {theme} 未在 THEMES 中")
            continue
        candidates.append((folder, theme))

    if args.limit:
        candidates = candidates[: args.limit]

    if not candidates:
        print("没有需要回填的期。")
        return 0

    print(f"待处理 {len(candidates)} 期（Pollinations 慢，每期约 15-60s）：")
    for folder, theme in candidates:
        print(f"  {folder.name}  (theme={theme})")

    if args.dry_run:
        print("\n[dry-run] 未调用 Pollinations")
        return 0

    ok_count = 0
    fail_count = 0
    for i, (folder, theme) in enumerate(candidates, start=1):
        print(f"\n[{i}/{len(candidates)}] {folder.name}")
        try:
            paths = engine.generate_multi_images(theme, str(folder))
            if paths:
                ok_count += 1
            else:
                fail_count += 1
        except Exception as e:
            print(f"  [fail] {e}")
            fail_count += 1
        if i < len(candidates):
            time.sleep(args.sleep)

    print(f"\n完成：{ok_count} 成功，{fail_count} 失败")
    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
