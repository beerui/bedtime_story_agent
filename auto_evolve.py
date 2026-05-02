#!/usr/bin/env python3
"""自动化自进化系统：评估→识别→改进→部署。

用法:
    python3 auto_evolve.py              # 运行一轮自进化
    python3 auto_evolve.py --dry-run    # 只分析，不执行
    python3 auto_evolve.py --threshold 50  # 质量阈值
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import time

from quality_score import score_episode, scan_outputs


def find_low_quality(outputs_dir: str, threshold: float) -> list:
    """找出低于阈值的内容。"""
    results = scan_outputs(outputs_dir)
    return [r for r in results if r['total'] < threshold]


def extract_theme(name: str) -> str:
    """从目录名提取纯净主题名。"""
    theme = re.sub(r'^Batch_\d{8}_\d{6}_', '', name)
    theme = re.sub(r'^EVOLVED_\d{8}_\d{6}_', '', theme)
    theme = re.sub(r'^REGEN_\d{8}_\d{6}_', '', theme)
    theme = re.sub(r'_EP\d+$', '', theme)
    return theme


def regenerate_episode(theme: str, outputs_dir: str, target_words: int = 900) -> dict:
    """重新生成一期内容。"""
    from story_gen import generate_story

    ts = time.strftime('%Y%m%d_%H%M%S')
    out_dir = os.path.join(outputs_dir, f'EVOLVED_{ts}_{theme}')
    os.makedirs(out_dir, exist_ok=True)

    story = generate_story(theme, out_dir, target_words)
    result = score_episode(story)
    result['theme'] = theme
    result['output_dir'] = out_dir
    return result


def replace_old_version(theme: str, new_dir: str, outputs_dir: str):
    """用新版本替换旧版本。"""
    # 找到旧版本目录（包括 Batch_, EVOLVED_, REGEN_ 前缀）
    for d in os.listdir(outputs_dir):
        if d == os.path.basename(new_dir):
            continue  # 跳过新版本目录
        old_theme = extract_theme(d)
        if old_theme == theme:
            old_path = os.path.join(outputs_dir, d)
            if os.path.isdir(old_path):
                shutil.rmtree(old_path)
                print(f'  已删除旧版本: {d}')


def rebuild_site(base_url: str = "https://beerui.github.io/bedtime_story_agent"):
    """重建站点。"""
    print('重建站点...')
    result = subprocess.run(
        ['python3', 'publish.py', '--copy-audio', '--base-url', base_url],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print('  站点重建完成')
    else:
        print(f'  站点重建失败: {result.stderr}')


def auto_evolve(outputs_dir: str, threshold: float, max_regenerate: int = 3, dry_run: bool = False):
    """运行一轮自进化。"""
    print(f'=== 自进化开始 ===')
    print(f'质量阈值: {threshold}')
    print(f'最大重新生成数: {max_regenerate}')
    print()

    # 1. 扫描现有内容
    all_results = scan_outputs(outputs_dir)
    print(f'总内容: {len(all_results)} 期')

    # 2. 找出低质量内容
    low_quality = [r for r in all_results if r['total'] < threshold]
    print(f'低质量（<{threshold} 分）: {len(low_quality)} 期')

    if not low_quality:
        print('没有需要改进的内容。')
        return

    # 3. 按分数排序，取最低的
    low_quality.sort(key=lambda x: x['total'])
    to_regenerate = low_quality[:max_regenerate]

    print(f'\n待重新生成: {len(to_regenerate)} 期')
    for r in to_regenerate:
        n = r.get('normalized', {})
        print(f'  {r["theme"]:25} | 总分 {r["total"]:5.1f} | 情绪 {n.get("emotion",0):5.1f}')

    if dry_run:
        print('\n[DRY RUN] 不执行实际操作。')
        return

    # 4. 重新生成
    print(f'\n开始重新生成...')
    regenerated = []
    for r in to_regenerate:
        theme = extract_theme(r['name'])
        print(f'  生成: {theme}...')
        try:
            new_result = regenerate_episode(theme, outputs_dir)
            regenerated.append((r, new_result))
            print(f'    完成: {new_result["total"]:.1f} 分')
        except Exception as e:
            print(f'    失败: {e}')

    # 5. 替换旧版本
    print(f'\n替换旧版本...')
    for old, new in regenerated:
        replace_old_version(old['theme'], new['output_dir'], outputs_dir)

    # 6. 重建站点
    rebuild_site()

    # 7. 报告
    print(f'\n=== 自进化完成 ===')
    print(f'重新生成: {len(regenerated)} 期')
    for old, new in regenerated:
        print(f'  {old["theme"]:25} | {old["total"]:5.1f} → {new["total"]:5.1f} | +{new["total"]-old["total"]:.1f}')


def main():
    parser = argparse.ArgumentParser(description='自动化自进化系统')
    parser.add_argument('--outputs', default='outputs', help='输出目录')
    parser.add_argument('--threshold', type=float, default=50, help='质量阈值')
    parser.add_argument('--max', type=int, default=3, help='最大重新生成数')
    parser.add_argument('--dry-run', action='store_true', help='只分析不执行')
    args = parser.parse_args()

    auto_evolve(args.outputs, args.threshold, args.max, args.dry_run)


if __name__ == '__main__':
    main()
