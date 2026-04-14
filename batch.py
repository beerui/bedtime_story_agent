#!/usr/bin/env python3
"""批量内容生产：一个命令生成多期助眠音频。

用法:
    # 从主题库随机选 3 期，每期 600 字
    python3 batch.py --count 3

    # 指定主题
    python3 batch.py --themes 午夜慢车 雨夜山中小屋 深海独潜

    # 全主题遍历
    python3 batch.py --all

    # 纯音频模式（跳过图片/视频/封面，速度快 3-5 倍）
    python3 batch.py --count 3 --audio-only

    # 调整字数
    python3 batch.py --count 2 --words 1000
"""
import argparse
import asyncio
import os
import random
import sys
import time
from datetime import datetime

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import THEMES, API_CONFIG
import engine

console = Console()


def _check_api_key():
    key = (API_CONFIG.get("proxy_api_key") or "").strip()
    if not key:
        console.print(
            "[bold red]错误：未检测到 API Key。请在 .env 中配置 DASHSCOPE_API_KEY。[/bold red]"
        )
        sys.exit(1)


async def produce_one(theme_name, output_dir, target_words, audio_only=False):
    """生产单期内容，返回结果摘要 dict。"""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs("assets", exist_ok=True)
    result = {"theme": theme_name, "output_dir": output_dir, "status": "OK"}
    t0 = time.time()

    try:
        # 1. 剧本
        story = await asyncio.to_thread(
            engine.generate_story, theme_name, output_dir, target_words
        )
        result["story_len"] = len(story)

        # 2. 语音 + BGM（并行）
        task_audio = engine.generate_audio(story, output_dir)
        task_bgm = asyncio.to_thread(engine.select_best_bgm, theme_name)
        (voice_file, subs), bgm_file = await asyncio.gather(task_audio, task_bgm)

        if not voice_file:
            result["status"] = "FAIL: 语音生成失败"
            return result

        result["voice_file"] = voice_file
        result["subtitle_count"] = len(subs)

        # 3. 成品混音
        final_audio = engine.mix_final_audio(voice_file, bgm_file, output_dir)
        result["final_audio"] = final_audio

        # 4. 视觉素材（可选）
        if not audio_only:
            images = await asyncio.to_thread(
                engine.generate_multi_images, theme_name, output_dir
            )
            result["images"] = images

            # 封面
            await asyncio.to_thread(
                engine.generate_and_crop_cover, theme_name, output_dir
            )

    except Exception as e:
        result["status"] = f"FAIL: {e}"

    result["duration_sec"] = time.time() - t0
    return result


async def batch_main(args):
    _check_api_key()

    # 确定要生产的主题列表
    if args.all:
        themes = list(THEMES.keys())
    elif args.themes:
        themes = []
        for t in args.themes:
            if t in THEMES:
                themes.append(t)
            else:
                console.print(f"[yellow]主题 '{t}' 不在主题库中，跳过[/yellow]")
    else:
        all_themes = list(THEMES.keys())
        themes = random.sample(all_themes, min(args.count, len(all_themes)))

    if not themes:
        console.print("[red]没有可用的主题[/red]")
        return

    console.print(
        Panel.fit(
            f"[bold]批量生产计划[/bold]\n"
            f"主题数: {len(themes)}\n"
            f"每期字数: ~{args.words}\n"
            f"模式: {'纯音频' if args.audio_only else '音频 + 视觉素材'}"
        )
    )

    results = []
    for i, theme in enumerate(themes):
        console.print(
            f"\n{'=' * 60}\n"
            f"[bold cyan]  [{i+1}/{len(themes)}] 正在生产：{theme}[/bold cyan]\n"
            f"{'=' * 60}"
        )
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = f"outputs/Batch_{ts}_{theme}"
        result = await produce_one(theme, output_dir, args.words, args.audio_only)
        results.append(result)

    # 汇总报告
    console.print(f"\n{'=' * 60}")
    table = Table(title="批量生产报告")
    table.add_column("主题", style="cyan")
    table.add_column("状态")
    table.add_column("字数", justify="right")
    table.add_column("耗时", justify="right")
    table.add_column("成品路径")

    for r in results:
        status_style = "green" if r["status"] == "OK" else "red"
        table.add_row(
            r["theme"],
            f"[{status_style}]{r['status']}[/{status_style}]",
            str(r.get("story_len", "-")),
            f"{r.get('duration_sec', 0):.0f}s",
            r.get("final_audio", "-"),
        )

    console.print(table)

    ok_count = sum(1 for r in results if r["status"] == "OK")
    console.print(
        f"\n[bold green]完成 {ok_count}/{len(results)} 期内容生产[/bold green]"
    )


def main():
    parser = argparse.ArgumentParser(description="批量助眠内容生产")
    parser.add_argument(
        "--themes", nargs="+", help="指定主题名（空格分隔）"
    )
    parser.add_argument(
        "--count", type=int, default=3, help="随机生成的期数（不指定 --themes 时生效）"
    )
    parser.add_argument(
        "--all", action="store_true", help="遍历所有主题"
    )
    parser.add_argument(
        "--words", type=int, default=600, help="每期目标字数"
    )
    parser.add_argument(
        "--audio-only", action="store_true", help="纯音频模式（跳过图片/视频/封面）"
    )
    args = parser.parse_args()

    try:
        asyncio.run(batch_main(args))
    except KeyboardInterrupt:
        console.print("\n[yellow]已中断[/yellow]")
        sys.exit(0)


if __name__ == "__main__":
    main()
