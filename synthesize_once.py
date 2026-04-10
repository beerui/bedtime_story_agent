#!/usr/bin/env python3
"""用 CosyVoice 将文字合成为本地 mp3（读 config.py 中的 cosyvoice_api_key）。

用法::

    python synthesize_once.py
    python synthesize_once.py "你想听的句子"
    python synthesize_once.py -o outputs/my.mp3 "第二句测试"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

TESTS_DIR = os.path.join(ROOT, "tests")
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="CosyVoice 单次语音合成")
    parser.add_argument(
        "text",
        nargs="*",
        default=["# 《午夜慢车》电台脚本 --- ## 🎙️ 开场（0:00-1:30） \n **[环境音：列车轨道的低沉节奏，间隔3秒]** \n 各位听众，晚安。我是你的午夜电台主播。"],
        help="要合成的文字（可多个词会拼接）",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=os.path.join(ROOT, "outputs", "synth_demo.mp3"),
        help="输出文件路径",
    )
    args = parser.parse_args()
    text = " ".join(args.text).strip() or "晚安。"

    import asyncio_compat

    asyncio_compat.ensure_to_thread()

    from config import API_CONFIG

    if not (API_CONFIG.get("cosyvoice_api_key") or "").strip():
        print("错误: 请在 config.py 的 API_CONFIG 中配置 cosyvoice_api_key", file=sys.stderr)
        sys.exit(1)

    from engine import _synthesize_cosyvoice

    out_abs = os.path.abspath(args.output)
    odir = os.path.dirname(out_abs)
    if odir:
        os.makedirs(odir, exist_ok=True)

    asyncio.run(_synthesize_cosyvoice(text, out_abs))
    size = os.path.getsize(out_abs)
    print(f"已写入: {out_abs} ({size} bytes)")


if __name__ == "__main__":
    main()
