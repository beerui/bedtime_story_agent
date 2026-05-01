# metadata_gen.py
"""元数据生成与质量校验。"""
import json
import logging
import os

from moviepy.editor import AudioFileClip
from rich.console import Console

from config import API_CONFIG, MI_API_KEY, MI_BASE_URL, MI_TEXT_MODEL, THEMES

console = Console()
logger = logging.getLogger(__name__)

from openai import OpenAI

# Qwen (DashScope) — 默认/fallback
text_client = OpenAI(
    api_key=API_CONFIG["proxy_api_key"],
    base_url=API_CONFIG["proxy_base_url"],
)

# MiMo LLM — 优先使用
_mimo_text_client: OpenAI | None = None
if MI_API_KEY:
    _mimo_text_client = OpenAI(api_key=MI_API_KEY, base_url=MI_BASE_URL)


def _llm_raw(prompt_text: str) -> str | None:
    """底层 LLM 调用，MiMo 优先，Qwen fallback。"""
    if _mimo_text_client is not None:
        try:
            resp = _mimo_text_client.chat.completions.create(
                model=MI_TEXT_MODEL,
                messages=[{"role": "user", "content": prompt_text}],
                stream=False,
            )
            content = resp.choices[0].message.content
            if content:
                return content
        except Exception as e:
            logger.warning("MiMo LLM 失败，fallback 到 Qwen: %s", e)

    try:
        return text_client.chat.completions.create(
            model=API_CONFIG["text_model"],
            messages=[{"role": "user", "content": prompt_text}],
            stream=False,
        ).choices[0].message.content
    except Exception:
        return None


def generate_publish_metadata(theme_name: str, story_text: str, output_dir: str) -> dict:
    """为每期内容生成发布元数据（标题/简介/标签），适配多平台。"""
    meta_path = os.path.join(output_dir, "metadata.json")
    if os.path.exists(meta_path):
        console.print(f"  [dim]元数据已存在，跳过[/dim]")
        with open(meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    console.print("\n[bold cyan][发布助手] 正在生成多平台发布元数据...[/bold cyan]")
    prompt = (
        f"你是短视频/播客内容运营专家。主题：【{theme_name}】\n"
        f"稿件开头：{story_text[:200]}\n\n"
        "请为这期助眠音频生成发布元数据，严格按以下 JSON 格式输出，不要输出其他内容：\n"
        "{\n"
        '  "title": "吸引点击的标题（15-25字，含情绪钩子）",\n'
        '  "subtitle": "副标题（10-15字，补充说明）",\n'
        '  "description_ximalaya": "喜马拉雅简介（50-80字，含SEO关键词）",\n'
        '  "description_bilibili": "B站简介（30-50字，年轻化口吻）",\n'
        '  "description_xiaoyuzhou": "小宇宙简介（40-60字，播客风格）",\n'
        '  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],\n'
        '  "category": "助眠/冥想/ASMR 三选一"\n'
        "}"
    )
    try:
        raw = _llm_raw(prompt)
        if not raw:
            raise ValueError("LLM 返回空")
        raw = raw.strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            metadata = json.loads(raw[start:end])
        else:
            metadata = {"title": theme_name, "tags": ["助眠", "深夜电台", "冥想"]}
    except Exception as e:
        console.print(f"[yellow]  元数据生成失败，使用默认值: {e}[/yellow]")
        metadata = {"title": theme_name, "tags": ["助眠", "深夜电台", "冥想"]}

    metadata["theme"] = theme_name
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    console.print(f"  标题: {metadata.get('title', '')}")
    console.print(f"  标签: {metadata.get('tags', [])}")
    return metadata


def validate_output(output_dir: str) -> tuple[bool, list[str]]:
    """校验一期内容的完整性和质量。"""
    issues = []

    required = ["story_draft.txt", "voice.mp3", "final_audio.mp3"]
    for f in required:
        path = os.path.join(output_dir, f)
        if not os.path.isfile(path):
            issues.append(f"缺失文件: {f}")
        elif os.path.getsize(path) == 0:
            issues.append(f"空文件: {f}")

    final = os.path.join(output_dir, "final_audio.mp3")
    if os.path.isfile(final) and os.path.getsize(final) > 0:
        try:
            clip = AudioFileClip(final)
            dur = clip.duration
            clip.close()
            if dur < 30:
                issues.append(f"音频过短: {dur:.0f}s (最低 30s)")
            size_mb = os.path.getsize(final) / 1024 / 1024
            if size_mb > 50:
                issues.append(f"文件过大: {size_mb:.1f}MB (上限 50MB)")
        except Exception as e:
            issues.append(f"音频无法读取: {e}")

    draft = os.path.join(output_dir, "story_draft.txt")
    if os.path.isfile(draft):
        with open(draft, "r", encoding="utf-8") as f:
            text = f.read()
        if "[阶段：" not in text and "【阶段：" not in text:
            issues.append("剧本缺少阶段标记")

    ok = len(issues) == 0
    if ok:
        console.print(f"  [green]质量校验通过[/green]")
    else:
        for iss in issues:
            console.print(f"  [red]校验问题: {iss}[/red]")
    return ok, issues
