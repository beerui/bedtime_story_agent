#!/usr/bin/env python3
"""内容质量自动评分系统：量化评估每期剧本的疗愈价值密度。

用法:
    python3 quality_score.py                    # 评估所有内容
    python3 quality_score.py --latest 5         # 评估最近 5 期
    python3 quality_score.py --theme 篝火与星空   # 评估特定主题
    python3 quality_score.py --threshold 70      # 只显示低于 70 分的
"""
import argparse
import json
import os
import re

# 价值词库
SENSORY_WORDS = [
    '听', '看', '闻', '触', '摸', '感受', '温', '凉', '暖', '冷', '湿', '干',
    '光', '暗', '声', '响', '静', '粗糙', '柔软', '沉重', '轻盈', '光滑', '粘',
    '烫', '冰', '热', '闷', '清新', '潮湿', '干燥', '刺', '痒', '麻', '酸',
]
EMOTION_WORDS = [
    '累', '怕', '慌', '焦虑', '紧张', '放松', '安全', '孤独', '平静', '释然',
    '释怀', '安宁', '疲惫', '烦躁', '恐惧', '悲伤', '温暖', '委屈', '压抑',
    '窒息', '无助', '迷茫', '愤怒', '厌倦', '麻木', '心安', '踏实', '松弛',
]
BODY_WORDS = [
    '肩膀', '呼吸', '胸口', '后颈', '太阳穴', '眼皮', '手指', '脚趾', '脊椎',
    '肌肉', '心跳', '脉搏', '腹部', '后背', '额头', '锁骨', '眉心', '下巴',
    '喉咙', '掌心', '膝盖', '脚踝', '腰', '头皮', '耳朵', '鼻子', '嘴唇',
]
PERMISSION_WORDS = [
    '允许', '可以', '不必', '不用', '不需要', '没关系', '不是你的错', '你值得',
    '你配得上', '你有权利', '放下', '翻篇', '就这样', '够了', '算了',
]
BREATHING_WORDS = ['呼吸', '吸气', '呼气', '气流', '吸', '呼', '吐气', '深呼吸']
METAPHOR_WORDS = ['像', '仿佛', '如同', '好像', '犹如', '宛如', '恰似']

# 评分权重
WEIGHTS = {
    'sensory': 0.20,      # 感官沉浸
    'emotion': 0.25,      # 情绪共鸣（最重要）
    'body': 0.20,         # 身体锚定
    'permission': 0.15,   # 心理许可
    'breathing': 0.10,    # 呼吸引导
    'structure': 0.10,    # 结构完整性
}


def count_density(text: str, words: list) -> float:
    """计算每千字的词频密度。"""
    if not text:
        return 0
    count = sum(text.count(w) for w in words)
    return count / len(text) * 1000


def check_structure(text: str) -> dict:
    """检查结构完整性。"""
    has_intro = bool(re.search(r'\[阶段：引入\]', text))
    has_deep = bool(re.search(r'\[阶段：深入\]', text))
    has_outro = bool(re.search(r'\[阶段：尾声\]', text))
    has_pauses = len(re.findall(r'\[停顿', text)) >= 3
    has_prosody = bool(re.search(r'\[慢速\]|\[轻声\]|\[极弱\]', text))
    has_env_sound = bool(re.search(r'\[环境音', text))

    score = sum([has_intro, has_deep, has_outro, has_pauses, has_prosody, has_env_sound]) / 6 * 100
    return {
        'score': score,
        'intro': has_intro,
        'deep': has_deep,
        'outro': has_outro,
        'pauses': has_pauses,
        'prosody': has_prosody,
        'env_sound': has_env_sound,
    }


def score_episode(text: str) -> dict:
    """评估单期内容，返回各维度分数和加权总分。"""
    chars = len(text)
    if chars < 100:
        return {'total': 0, 'error': '内容过短'}

    metrics = {
        'sensory': count_density(text, SENSORY_WORDS),
        'emotion': count_density(text, EMOTION_WORDS),
        'body': count_density(text, BODY_WORDS),
        'permission': count_density(text, PERMISSION_WORDS),
        'breathing': count_density(text, BREATHING_WORDS),
    }
    structure = check_structure(text)

    # 归一化到 0-100（基于经验值的合理上限）
    norm = {
        'sensory': min(100, metrics['sensory'] / 40 * 100),
        'emotion': min(100, metrics['emotion'] / 10 * 100),
        'body': min(100, metrics['body'] / 12 * 100),
        'permission': min(100, metrics['permission'] / 10 * 100),
        'breathing': min(100, metrics['breathing'] / 6 * 100),
        'structure': structure['score'],
    }

    total = sum(norm[k] * WEIGHTS[k] for k in WEIGHTS)

    return {
        'total': round(total, 1),
        'metrics': {k: round(v, 2) for k, v in metrics.items()},
        'normalized': {k: round(v, 1) for k, v in norm.items()},
        'structure': structure,
        'chars': chars,
    }


def scan_outputs(outputs_dir: str) -> list:
    """扫描 outputs/ 目录，返回所有期的评分。"""
    results = []
    for d in sorted(os.listdir(outputs_dir)):
        ep_path = os.path.join(outputs_dir, d)
        if not os.path.isdir(ep_path) or d.startswith('.'):
            continue

        for fname in ['story_draft.txt', 'story.txt']:
            p = os.path.join(ep_path, fname)
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    text = f.read()
                theme = re.sub(r'^Batch_\d{8}_\d{6}_', '', d)
                theme = re.sub(r'^EVOLVED_\d{8}_\d{6}_', '', theme)
                theme = re.sub(r'^REGEN_\d{8}_\d{6}_', '', theme)
                theme = re.sub(r'_EP\d+$', '', theme)
                if not theme or theme == 'TEST_RUN':
                    continue

                result = score_episode(text)
                result['name'] = d
                result['theme'] = theme
                results.append(result)
                break

    return results


def print_report(results: list, threshold: float = 0):
    """打印评分报告。"""
    if threshold > 0:
        results = [r for r in results if r['total'] < threshold]

    if not results:
        print('没有符合条件的内容。')
        return

    # 按分数排序
    results.sort(key=lambda x: x['total'])

    print(f'{"主题":25} | {"总分":6} | {"感官":6} | {"情绪":6} | {"身体":6} | {"许可":6} | {"呼吸":6} | {"结构":6}')
    print('-' * 100)

    for r in results:
        n = r.get('normalized', {})
        print(
            f'{r["theme"]:25} | {r["total"]:6.1f} | '
            f'{n.get("sensory", 0):6.1f} | {n.get("emotion", 0):6.1f} | '
            f'{n.get("body", 0):6.1f} | {n.get("permission", 0):6.1f} | '
            f'{n.get("breathing", 0):6.1f} | {n.get("structure", 0):6.1f}'
        )

    # 统计
    scores = [r['total'] for r in results]
    print(f'\n总计: {len(results)} 期')
    print(f'平均分: {sum(scores)/len(scores):.1f}')
    print(f'最高分: {max(scores):.1f}')
    print(f'最低分: {min(scores):.1f}')
    if threshold > 0:
        print(f'低于 {threshold} 分: {len(results)} 期')


def main():
    parser = argparse.ArgumentParser(description='内容质量自动评分')
    parser.add_argument('--outputs', default='outputs', help='输出目录')
    parser.add_argument('--latest', type=int, default=0, help='只评估最近 N 期')
    parser.add_argument('--theme', type=str, default='', help='只评估特定主题')
    parser.add_argument('--threshold', type=float, default=0, help='只显示低于此分数的')
    parser.add_argument('--json', action='store_true', help='输出 JSON 格式')
    args = parser.parse_args()

    results = scan_outputs(args.outputs)

    if args.theme:
        results = [r for r in results if args.theme in r['theme']]
    if args.latest > 0:
        results = results[-args.latest:]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        print_report(results, threshold=args.threshold)


if __name__ == '__main__':
    main()
