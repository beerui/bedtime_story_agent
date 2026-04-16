#!/usr/bin/env python3
"""批量对现有 outputs/Batch_*/final_audio.mp3 做 LUFS 响度归一。

幂等——已归一过的文件再跑结果一样。默认目标 -22 LUFS。

用法:
    python3 backfill_loudness.py                  # 归一全部
    python3 backfill_loudness.py --dry-run        # 只测量不改
    python3 backfill_loudness.py --target -20     # 改目标
    python3 backfill_loudness.py --only 午夜慢车   # 过滤子串
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="只测量，不修改")
    parser.add_argument("--target", type=float, default=None, help="目标 LUFS（默认 audio_fx.DEFAULT_TARGET_LUFS）")
    parser.add_argument("--only", help="只处理文件夹名包含此子串的期")
    args = parser.parse_args()

    try:
        import audio_fx
    except Exception as e:
        print(f"audio_fx 导入失败: {e}", file=sys.stderr)
        return 1
    if not audio_fx.available():
        print("ffmpeg 不可用——请装系统 ffmpeg 或 imageio_ffmpeg", file=sys.stderr)
        return 1

    target = args.target if args.target is not None else audio_fx.DEFAULT_TARGET_LUFS
    outputs = Path(__file__).parent / "outputs"
    if not outputs.is_dir():
        print("outputs/ 不存在")
        return 1

    mp3s: list[Path] = []
    for folder in sorted(outputs.iterdir()):
        if not folder.is_dir() or not folder.name.startswith("Batch_"):
            continue
        if args.only and args.only not in folder.name:
            continue
        mp3 = folder / "final_audio.mp3"
        if mp3.is_file():
            mp3s.append(mp3)

    if not mp3s:
        print("没有符合条件的 mp3")
        return 0

    print(f"扫描到 {len(mp3s)} 个 final_audio.mp3，目标 {target} LUFS" + (" (dry-run)" if args.dry_run else ""))
    print()

    changed = 0
    skipped = 0
    failed = 0
    measurements: list[float] = []

    for mp3 in mp3s:
        before = audio_fx.measure_lufs(mp3)
        if before is None:
            print(f"  [fail] {mp3.parent.name}  无法测量")
            failed += 1
            continue
        measurements.append(before)
        label = mp3.parent.name.split("_", 3)[-1]
        gap = abs(before - target)

        if args.dry_run:
            marker = "→" if gap > 0.5 else "✓"
            print(f"  {marker} {before:+.1f} LUFS  {label[:50]}")
            continue

        # If already within 0.5 LUFS, skip re-encoding (preserves quality)
        if gap < 0.5:
            print(f"  [skip] {before:+.1f}→{before:+.1f}  {label[:50]}  (已达标)")
            skipped += 1
            continue

        ok = audio_fx.normalize_mp3(mp3, target_lufs=target)
        if not ok:
            print(f"  [fail] {label[:50]}  ffmpeg loudnorm 失败")
            failed += 1
            continue
        after = audio_fx.measure_lufs(mp3)
        after_str = f"{after:+.1f}" if after is not None else "?"
        print(f"  [ok]   {before:+.1f} → {after_str}  {label[:50]}")
        changed += 1

    import statistics
    print()
    if measurements:
        print(f"源响度: min={min(measurements):.1f}  max={max(measurements):.1f}  "
              f"mean={statistics.mean(measurements):.1f}  "
              f"spread={max(measurements)-min(measurements):.1f} dB")
    if not args.dry_run:
        print(f"共 {len(mp3s)} 个：{changed} 归一，{skipped} 跳过，{failed} 失败")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
