# theme_gen.py
"""动态主题生成器：基于市场趋势和用户画像生成新助眠主题。"""
import json
import logging
import os
import re

from rich.console import Console

from config import THEMES, THEME_CATEGORIES

console = Console()
logger = logging.getLogger(__name__)


def _llm_raw(prompt_text: str) -> str | None:
    """复用 story_gen 的 LLM 调用（MiMo 优先 + Qwen fallback）。"""
    from story_gen import _llm_raw as _raw
    return _raw(prompt_text)


# 自定义主题持久化路径
CUSTOM_THEMES_PATH = os.path.join(os.path.dirname(__file__), "custom_themes.json")


def load_custom_themes() -> dict:
    """加载已生成的自定义主题。"""
    if os.path.exists(CUSTOM_THEMES_PATH):
        try:
            with open(CUSTOM_THEMES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_custom_themes(themes: dict) -> None:
    """持久化自定义主题。"""
    with open(CUSTOM_THEMES_PATH, "w", encoding="utf-8") as f:
        json.dump(themes, f, ensure_ascii=False, indent=2)


def generate_themes(count: int = 5, focus: str = "") -> list[str]:
    """通过 LLM 生成新主题，返回新主题名列表。

    Args:
        count: 生成数量
        focus: 可选聚焦方向，如 "职场"、"2026科技焦虑"
    """
    existing = list(THEMES.keys()) + list(load_custom_themes().keys())
    existing_block = "、".join(existing[:20])

    category_desc = "\n".join(
        f"- {k}: {v['label']} — {v['description']}"
        for k, v in THEME_CATEGORIES.items()
    )

    focus_block = f"\n【聚焦方向】{focus}" if focus else ""

    prompt = f"""你是助眠内容产品经理，擅长发现 2026 年当下人群的睡眠痛点。

已有主题（不可重复）：{existing_block}

主题分类：
{category_desc}
{focus_block}

请生成 {count} 个全新的助眠主题。每个主题必须满足：
1. 对应一个真实的、具体的睡眠痛点场景（不是泛泛的"放松"）
2. 有明确的心理学/感官技术支撑
3. 有高搜索量的关键词（SEO）
4. 场景有电影感画面（可生成封面图）

严格按以下 JSON 数组格式输出，不要有其他内容：
[
  {{
    "name": "主题名（简短有画面感）",
    "story_prompt": "详细的口播稿设定（100-150字，包含场景、情绪、感官细节）",
    "image_prompt": "英文封面图提示词（cinematic vertical view, relaxing, photorealistic）",
    "bgm_file": "",
    "category": "nature_relax / clinical_technique / emotional_resonance / zeitgeist_2026 四选一",
    "pain_point": "一句话描述听众此刻的具体感受",
    "technique": "使用的心理学/感官技术名称",
    "search_keywords": ["关键词1", "关键词2", "关键词3", "关键词4", "关键词5"],
    "ideal_duration_min": 12,
    "emotional_target": "听完后希望达到的情绪状态"
  }}
]"""

    raw = _llm_raw(prompt)
    if not raw:
        console.print("[red]主题生成失败：LLM 无响应[/red]")
        return []

    # 提取 JSON 数组
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw, flags=re.MULTILINE).strip()

    try:
        themes_data = json.loads(raw)
    except Exception:
        m = re.search(r"\[[\s\S]*\]", raw)
        if not m:
            console.print("[red]主题生成失败：无法解析 JSON[/red]")
            return []
        try:
            themes_data = json.loads(m.group(0))
        except Exception:
            console.print("[red]主题生成失败：JSON 格式错误[/red]")
            return []

    if not isinstance(themes_data, list):
        return []

    # 合并到 THEMES 并持久化
    custom = load_custom_themes()
    new_names = []
    for t in themes_data:
        name = t.get("name", "").strip()
        if not name or name in THEMES or name in custom:
            continue
        theme_cfg = {
            "story_prompt": t.get("story_prompt", ""),
            "image_prompt": t.get("image_prompt", ""),
            "bgm_file": t.get("bgm_file", ""),
            "category": t.get("category", "emotional_resonance"),
            "pain_point": t.get("pain_point", ""),
            "technique": t.get("technique", ""),
            "search_keywords": t.get("search_keywords", []),
            "ideal_duration_min": t.get("ideal_duration_min", 12),
            "emotional_target": t.get("emotional_target", ""),
        }
        custom[name] = theme_cfg
        THEMES[name] = theme_cfg
        new_names.append(name)

    if new_names:
        save_custom_themes(custom)
        console.print(f"[green]  生成 {len(new_names)} 个新主题: {'、'.join(new_names)}[/green]")

    return new_names


def ensure_themes(count: int, focus: str = "") -> list[str]:
    """确保主题库至少有 count 个可用主题，不足时自动生成。

    返回可用主题名列表（包含已有 + 新生成的）。
    """
    all_themes = list(THEMES.keys())
    if len(all_themes) >= count:
        return all_themes

    need = count - len(all_themes)
    console.print(f"[yellow]主题库仅 {len(all_themes)} 个，需要再生成 {need} 个...[/yellow]")
    generate_themes(need, focus=focus)
    return list(THEMES.keys())
