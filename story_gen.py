# story_gen.py
"""故事生成引擎：3-pass LLM 剧本生成 + 质量评估 + 章节标题。"""
import json
import logging
import os
import re

from rich.console import Console

from config import API_CONFIG, MI_API_KEY, MI_BASE_URL, MI_TEXT_MODEL, THEMES, TTS_SCRIPT_DIRECTIVE

console = Console()
logger = logging.getLogger(__name__)

from openai import OpenAI

# Qwen (DashScope) — 默认/fallback
text_client = OpenAI(
    api_key=API_CONFIG["proxy_api_key"],
    base_url=API_CONFIG["proxy_base_url"],
)

# MiMo LLM — 优先使用（如果配置了 key）
_mimo_text_client: OpenAI | None = None
if MI_API_KEY:
    _mimo_text_client = OpenAI(api_key=MI_API_KEY, base_url=MI_BASE_URL)


def _llm_call(prompt_text: str, step_name: str) -> str:
    """统一 LLM 调用。MiMo 优先，失败自动 fallback 到 Qwen。"""
    content = _llm_raw(prompt_text)
    if content is None:
        console.print(f"[bold red]剧本生成第 {step_name} 步 API 调用失败: 所有引擎均不可用[/bold red]")
        raise RuntimeError(f"LLM 调用失败: {step_name}")
    return content


def _llm_raw(prompt_text: str) -> str | None:
    """底层 LLM 调用，返回文本或 None。MiMo 优先，Qwen fallback。"""
    # MiMo LLM
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

    # Qwen (DashScope)
    try:
        return text_client.chat.completions.create(
            model=API_CONFIG["text_model"],
            messages=[{"role": "user", "content": prompt_text}],
            stream=False,
        ).choices[0].message.content
    except Exception:
        return None


def generate_story(theme_name: str, output_dir: str, target_words: int, extra_prompt: str = "") -> str:
    """3-pass 剧本生成：大纲 → 扩写 → 润色，低分自动重写。"""
    text_path = os.path.join(output_dir, "story_draft.txt")
    if os.path.exists(text_path):
        with open(text_path, "r", encoding="utf-8") as f:
            return f.read()

    theme_info = THEMES[theme_name]
    theme_brief = theme_info.get("story_prompt", "")
    pain_point = theme_info.get("pain_point", "").strip()
    technique = theme_info.get("technique", "").strip()
    emotional_target = theme_info.get("emotional_target", "").strip()
    meta_parts = []
    if pain_point:
        meta_parts.append(f"- 听众此刻的感受：{pain_point}")
    if technique:
        meta_parts.append(f"- 使用的心理/感官技术：{technique}")
    if emotional_target:
        meta_parts.append(f"- 听完后希望达到的状态：{emotional_target}")
    meta_block = ""
    if meta_parts:
        meta_block = (
            "\n【听众心理锚点 — 核心生产依据，必须回应】\n"
            + "\n".join(meta_parts)
            + "\n"
        )

    spec = TTS_SCRIPT_DIRECTIVE

    outline = _llm_call(
        f"你是睡眠冥想心理学家。主题【{theme_name}】。\n"
        f"主题氛围要求：{theme_brief}\n"
        f"{meta_block}\n{spec}\n\n"
        "请写「三段式心理暗示大纲」，明确标注 [阶段：引入]、[阶段：深入]、[阶段：尾声] 三个阶段的分界。"
        "大纲必须说明：引入段如何承认听众的当下感受（不回避、不说教），深入段如何用上面列出的技术帮助听众，"
        "尾声段如何把听众带到目标状态。"
        f"大纲里标注计划在何处用 [环境音：] 与 [停顿]。{extra_prompt}",
        "1/大纲",
    )
    draft = _llm_call(
        f"你是深夜电台主播，声音要慢、稳、催眠感。\n{meta_block}\n{spec}\n\n"
        f"根据大纲扩写成完整口播稿（约 {target_words} 字量级）：\n{outline}\n\n"
        "要求：\n"
        "1) 必须在正文对应位置保留 [阶段：引入]、[阶段：深入]、[阶段：尾声] 标记。\n"
        "2) 必须实际写出 [环境音：…]、[停顿] 或 [停顿500ms]/[停顿1s] 等标记，位置要自然。\n"
        "3) 禁止 [叹气][轻笑] 等会被念出来的方括号拟声词。\n"
        "4) 如果上面列出了「听众此刻的感受」，引入段必须至少出现一次对这个感受的具体承认（不是笼统的「今天辛苦了」，"
        "要映射到那个具体情境——例如裁员主题就直接承认「工位的杂物还散落在地」这类具体画面）。",
        "2/扩写",
    )
    final_story = _llm_call(
        f"你是严苛主编：去掉 AI 腔与说教感，增强电影感与感官描写。\n{meta_block}\n{spec}\n\n"
        "保留初稿中所有 [阶段：]、[环境音：]、[停顿…]、[慢速]、[轻声]、[极弱] 标记，不得删除或改成自然语言描述；可微调措辞与标点。\n\n"
        "【禁止清单】：\n"
        "- 排比不超过两组\n"
        "- 不以反问句结尾\n"
        "- 禁止「让我们」「我们一起」等集体感措辞\n"
        "- 禁止「你有没有想过」「其实」等说教开头\n"
        "- 每段至少一个具体感官细节（触觉/嗅觉/温度/声音质感）\n"
        "- 如果上面有「听众此刻的感受」，剧本必须直接承认这个感受，而不是用积极情绪覆盖它——承认比安慰更能让人放松\n\n"
        f"初稿：\n{draft}",
        "3/润色",
    )

    # 质量评估 + 低分自动重写（最多重试 1 次）
    score, feedback = _evaluate_story(final_story, theme_name)
    if score < 70:
        console.print(f"[yellow]  剧本评分 {score}/100 低于阈值，启动重写...[/yellow]")
        console.print(f"  [dim]反馈: {feedback}[/dim]")
        final_story = _llm_call(
            f"你是严苛主编。以下剧本评分偏低，请根据反馈修改。\n{meta_block}\n{spec}\n\n"
            f"【评审反馈】：\n{feedback}\n\n"
            "保留所有 [阶段：]、[环境音：]、[停顿…]、[慢速]、[轻声]、[极弱] 标记。\n\n"
            f"原稿：\n{final_story}",
            "4/重写",
        )
        score2, _ = _evaluate_story(final_story, theme_name)
        console.print(f"  重写后评分: {score2}/100")
    else:
        console.print(f"  [green]剧本评分: {score}/100[/green]")

    with open(text_path, "w", encoding="utf-8") as f:
        f.write(final_story)

    # 章节标题（可选，best-effort）
    try:
        titles = _generate_chapter_titles(final_story, theme_name)
        if titles:
            titles_path = os.path.join(output_dir, "chapter_titles.json")
            with open(titles_path, "w", encoding="utf-8") as f:
                json.dump(titles, f, ensure_ascii=False, indent=2)
            console.print(f"  [dim]章节标题: {' / '.join(titles.values())}[/dim]")
    except Exception as e:
        console.print(f"  [yellow]章节标题生成失败（忽略）: {e}[/yellow]")

    return final_story


def _generate_chapter_titles(story_text: str, theme_name: str) -> dict:
    """用 LLM 为引入/深入/尾声三段取简短章节标题。"""
    prompt = (
        f"以下是助眠剧本《{theme_name}》。剧本分为 [阶段：引入]、[阶段：深入]、[阶段：尾声] 三段。"
        "请为每段取一个 5-10 字的章节标题——要具体、抓住该段核心画面/动作/情绪。"
        "例如：承认焦虑 / 指尖棉线纹路 / 你在这里。避免「放松 / 引导 / 冥想」这类抽象词。\n\n"
        "严格按以下 JSON 格式输出，不要有任何前后缀或 markdown 围栏：\n"
        '{"引入": "...", "深入": "...", "尾声": "..."}\n\n'
        f"剧本内容：\n{story_text[:2400]}"
    )
    raw = _llm_raw(prompt)
    if not raw:
        return {}
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw, flags=re.MULTILINE).strip()

    try:
        titles = json.loads(raw)
    except Exception:
        m = re.search(r"\{[^{}]*\}", raw, flags=re.DOTALL)
        if not m:
            return {}
        try:
            titles = json.loads(m.group(0))
        except Exception:
            return {}

    out: dict[str, str] = {}
    for k in ("引入", "深入", "尾声"):
        v = titles.get(k)
        if isinstance(v, str):
            v = v.strip().strip("「」\"'『』[]【】").strip()
            if 0 < len(v) <= 24:
                out[k] = v
    return out


def _evaluate_story(story_text: str, theme_name: str) -> tuple[int, str]:
    """用 LLM 对剧本做催眠质量评分，返回 (score, feedback)。"""
    theme_info = THEMES.get(theme_name, {})
    pain_point = theme_info.get("pain_point", "").strip()
    technique = theme_info.get("technique", "").strip()
    target = theme_info.get("emotional_target", "").strip()
    anchor_block = ""
    if pain_point or technique or target:
        lines = []
        if pain_point:
            lines.append(f"  痛点：{pain_point}")
        if technique:
            lines.append(f"  技术：{technique}")
        if target:
            lines.append(f"  目标状态：{target}")
        anchor_block = "\n本期主题的心理锚点：\n" + "\n".join(lines) + "\n"

    prompt = (
        f"你是助眠内容质量审核专家。请对以下【{theme_name}】主题的助眠剧本做评估。\n"
        f"{anchor_block}\n"
        "评分维度（每项 0-20 分，满分 100）：\n"
        "1) 催眠感：语言节奏是否越来越慢、是否有渐进式放松引导\n"
        "2) 感官描写：是否有具体的触觉/嗅觉/温度/声音质感描写\n"
        "3) 节奏标记：[停顿]、[环境音]、[慢速]、[极弱] 等标记使用是否自然且渐进\n"
        "4) 去AI腔：是否避免了排比、说教、集体措辞等 AI 痕迹\n"
        "5) 痛点对齐：是否承认了上面「痛点」描述的感受（而不是用正能量覆盖），是否用上了"
        "「技术」所描述的心理/感官手法，结尾是否真正把听众带到「目标状态」\n\n"
        "严格按以下格式输出，不要输出其他内容：\n"
        "总分：XX\n"
        "反馈：一句话改进建议（必须点出最低分的维度）\n\n"
        f"剧本：\n{story_text[:1800]}"
    )
    try:
        raw = _llm_raw(prompt)
        if not raw:
            return 75, ""
        raw = raw.strip()
        score = 75
        feedback = ""
        for line in raw.split("\n"):
            line = line.strip()
            if "总分" in line:
                m = re.search(r"(\d+)", line)
                if m:
                    score = min(100, max(0, int(m.group(1))))
            elif "反馈" in line:
                feedback = line.split("：", 1)[-1].split(":", 1)[-1].strip()
        return score, feedback
    except Exception:
        return 75, ""


def generate_custom_theme(user_idea: str) -> str:
    """AI 现场编一个新主题场景。"""
    user_idea = user_idea.encode("utf-8", "ignore").decode("utf-8")
    prompt = (
        f"你是一个睡眠冥想场景规划师。用户想法：【{user_idea}】。\n\n{TTS_SCRIPT_DIRECTIVE}\n\n"
        "「文案设定」需写成适合口播的设定，并在设定中体现会在成稿里使用的 [环境音：]、[停顿] 等节奏设计。\n"
        "严格按3行格式输出：\n主题名：\n文案设定：\n画面提示词：(英文，包含 cinematic vertical view, relaxing)\n"
    )
    try:
        result_text = _llm_raw(prompt)
        if not result_text:
            console.print("[bold red]文本生成 API 调用失败: 所有引擎均不可用[/bold red]")
            raise SystemExit(1)
        result_text = result_text.strip()
    except SystemExit:
        raise
    except Exception as e:
        console.print(f"[bold red]文本生成 API 调用失败: {e}[/bold red]")
        raise SystemExit(1)

    new_theme_name = "未命名自定义主题"
    new_story_prompt = f"关于{user_idea}的场景。要求温柔舒缓。"
    new_image_prompt = f"A cinematic vertical view of {user_idea}, relaxing, highly detailed, 4k."
    for line in result_text.split("\n"):
        line = line.strip().replace("**", "")
        if "主题名" in line:
            new_theme_name = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif "文案设定" in line:
            new_story_prompt = line.split(":", 1)[-1].split("：", 1)[-1].strip()
        elif "画面提示词" in line:
            new_image_prompt = line.split(":", 1)[-1].split("：", 1)[-1].strip()

    console.print(f"[green]  ✨ 新主题研发成功：【{new_theme_name}】[/green]")
    THEMES[new_theme_name] = {
        "story_prompt": new_story_prompt,
        "image_prompt": new_image_prompt,
        "bgm_file": "",
    }
    return new_theme_name
