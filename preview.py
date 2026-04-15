#!/usr/bin/env python3
"""查看所有已生产内容的状态摘要。

用法:
    python3 preview.py              # 列出所有产出
    python3 preview.py --latest 5   # 只看最近 5 期
    python3 preview.py --check      # 包含质量校验
"""
import argparse
import json
import os
import sys

from rich.console import Console
from rich.table import Table

console = Console()


def scan_outputs(outputs_dir="outputs", limit=None, check=False):
    if not os.path.isdir(outputs_dir):
        console.print("[red]outputs/ 目录不存在[/red]")
        return

    folders = sorted(
        [f for f in os.listdir(outputs_dir) if os.path.isdir(os.path.join(outputs_dir, f))],
        reverse=True,
    )
    if limit:
        folders = folders[:limit]

    if not folders:
        console.print("[yellow]没有已生产的内容[/yellow]")
        return

    table = Table(title=f"内容库 ({len(folders)} 期)")
    table.add_column("#", justify="right", style="dim")
    table.add_column("主题", style="cyan")
    table.add_column("标题")
    table.add_column("字数", justify="right")
    table.add_column("音频", justify="center")
    table.add_column("字幕", justify="center")
    table.add_column("封面", justify="center")
    if check:
        table.add_column("校验", justify="center")

    for i, folder in enumerate(folders, 1):
        path = os.path.join(outputs_dir, folder)

        # 读取元数据
        meta_path = os.path.join(path, "metadata.json")
        title = "-"
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                title = meta.get("title", "-")[:25]
            except Exception:
                pass

        # 统计文件
        draft = os.path.join(path, "story_draft.txt")
        word_count = "-"
        if os.path.isfile(draft):
            with open(draft, "r", encoding="utf-8") as f:
                word_count = str(len(f.read()))

        has_audio = "OK" if os.path.isfile(os.path.join(path, "final_audio.mp3")) else "-"
        has_srt = "OK" if os.path.isfile(os.path.join(path, "subtitles.srt")) else "-"
        has_cover = "OK" if any(f.startswith("Cover_") for f in os.listdir(path)) else "-"

        # 从文件夹名提取主题
        parts = folder.split("_", 3)
        theme = parts[3] if len(parts) >= 4 else folder

        row = [str(i), theme[:12], title, word_count]
        row.append("[green]OK[/green]" if has_audio == "OK" else "[red]-[/red]")
        row.append("[green]OK[/green]" if has_srt == "OK" else "[dim]-[/dim]")
        row.append("[green]OK[/green]" if has_cover == "OK" else "[dim]-[/dim]")

        if check:
            issues = []
            if has_audio != "OK":
                issues.append("无音频")
            final = os.path.join(path, "final_audio.mp3")
            if os.path.isfile(final):
                size_mb = os.path.getsize(final) / 1024 / 1024
                if size_mb < 0.1:
                    issues.append("音频过小")
            if not os.path.isfile(draft):
                issues.append("无剧本")
            row.append("[red]" + "; ".join(issues) + "[/red]" if issues else "[green]OK[/green]")

        table.add_row(*row)

    console.print(table)

    # 统计
    total_audio = sum(
        1 for f in folders
        if os.path.isfile(os.path.join(outputs_dir, f, "final_audio.mp3"))
    )
    total_size = sum(
        os.path.getsize(os.path.join(outputs_dir, f, "final_audio.mp3"))
        for f in folders
        if os.path.isfile(os.path.join(outputs_dir, f, "final_audio.mp3"))
    ) / 1024 / 1024
    console.print(f"\n[dim]可发布音频: {total_audio} 期 | 总大小: {total_size:.1f}MB[/dim]")


def main():
    parser = argparse.ArgumentParser(description="查看已生产内容状态")
    parser.add_argument("--latest", type=int, help="只显示最近 N 期")
    parser.add_argument("--check", action="store_true", help="包含质量校验")
    args = parser.parse_args()
    scan_outputs(limit=args.latest, check=args.check)


if __name__ == "__main__":
    main()
