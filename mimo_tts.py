# mimo_tts.py
"""MiMo-V2.5-TTS 语音合成模块：集成小米 MiMo TTS API。

支持两种模式：
  1. 预置音色 (preset) — 使用 mimo-v2.5-tts 模型 + 内置 voice ID
  2. Voice Design    — 使用 mimo-v2.5-tts-voicedesign 模型 + 自然语言音色描述

统一入口: synthesize_mimo(text, output_path, voice=None, style=None, model=None)
  - 成功返回 True，失败返回 False（不抛异常）
"""
import asyncio
import base64
import logging
import os

from openai import OpenAI

from config import (
    MI_API_KEY,
    MI_BASE_URL,
    MIMO_AUDIO_TAGS,
    MIMO_PRESET_VOICES,
    MIMO_STYLE_TEMPLATES,
)

logger = logging.getLogger(__name__)

# 模型常量
MODEL_PRESET = "mimo-v2.5-tts"
MODEL_VOICE_DESIGN = "mimo-v2.5-tts-voicedesign"

# 默认预置音色（中文女声，适合睡前故事）
DEFAULT_VOICE = "冰糖"


def _get_client() -> OpenAI | None:
    """创建 MiMo API 客户端。缺少 key 时返回 None。"""
    api_key = MI_API_KEY
    if not api_key:
        logger.warning("MI_API_KEY 未配置，无法调用 MiMo TTS")
        return None
    return OpenAI(api_key=api_key, base_url=MI_BASE_URL)


def _resolve_model(voice: str | None, model: str | None) -> str:
    """根据参数自动选择模型。

    - 显式指定 model → 直接使用
    - voice 在预置音色表中 → preset 模型
    - 否则 → voicedesign 模型
    """
    if model:
        return model
    if voice and voice in MIMO_PRESET_VOICES:
        return MODEL_PRESET
    if voice is None:
        return MODEL_PRESET
    return MODEL_VOICE_DESIGN


def _build_messages(
    text: str,
    style: str | None,
    voice: str | None,
    model: str,
) -> list[dict]:
    """构建 MiMo API 的 messages 数组。

    两层控制：
      - user content: 全局风格指令（style 参数 或 voice design 描述）
      - assistant content: 待合成文本（可含音频标签前缀）
    """
    messages = []

    # User 角色: 风格指令
    if model == MODEL_VOICE_DESIGN and voice:
        # Voice Design 模式: voice 参数作为音色描述
        user_content = voice
        if style:
            user_content = f"{user_content}，{style}"
    else:
        # 预置音色模式: style 作为风格指令
        user_content = style or "用自然温柔的语调朗读"

    messages.append({"role": "user", "content": user_content})

    # Assistant 角色: 待合成文本
    messages.append({"role": "assistant", "content": text})

    return messages


def _build_request_kwargs(
    model: str,
    messages: list[dict],
    voice: str | None,
) -> dict:
    """构建 API 请求的关键字参数。"""
    kwargs = {
        "model": model,
        "messages": messages,
        "stream": False,
        "extra_body": {
            "audio": {
                "format": "wav",
            },
        },
    }

    # 预置音色模型需要 voice 参数
    if model == MODEL_PRESET:
        voice_id = voice if voice in MIMO_PRESET_VOICES else DEFAULT_VOICE
        kwargs["extra_body"]["audio"]["voice"] = voice_id

    return kwargs


def synthesize_mimo(
    text: str,
    output_path: str,
    voice: str | None = None,
    style: str | None = None,
    model: str | None = None,
) -> bool:
    """同步入口：调用 MiMo TTS API 合成语音。

    Args:
        text: 待合成文本
        output_path: 输出音频文件路径 (.wav)
        voice: 预置音色 ID 或 Voice Design 描述
        style: 风格标签（如 "温柔 慵懒"）或导演模式指令
        model: 指定模型，None 则自动选择

    Returns:
        True 成功，False 失败（不抛异常）
    """
    if not text or not text.strip():
        logger.error("synthesize_mimo: text 为空")
        return False

    client = _get_client()
    if client is None:
        return False

    resolved_model = _resolve_model(voice, model)
    messages = _build_messages(text, style, voice, resolved_model)
    kwargs = _build_request_kwargs(resolved_model, messages, voice)

    try:
        response = client.chat.completions.create(**kwargs)

        # 从响应中提取 base64 音频数据
        audio_data = None
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            audio_obj = getattr(choice.message, "audio", None)
            if audio_obj:
                # audio 可能是 dict 或对象
                if isinstance(audio_obj, dict):
                    audio_data = audio_obj.get("data")
                else:
                    audio_data = getattr(audio_obj, "data", None)

        if not audio_data:
            logger.error("MiMo TTS 返回了空的音频数据")
            return False

        # base64 解码并写入文件
        wav_bytes = base64.b64decode(audio_data)
        if not wav_bytes:
            logger.error("MiMo TTS base64 解码后为空")
            return False

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(wav_bytes)

        return True

    except Exception as e:
        logger.error("MiMo TTS 合成失败: %s", e)
        return False


async def synthesize_mimo_async(
    text: str,
    output_path: str,
    voice: str | None = None,
    style: str | None = None,
    model: str | None = None,
) -> bool:
    """异步入口：包装同步调用，避免阻塞事件循环。"""
    return await asyncio.to_thread(
        synthesize_mimo, text, output_path, voice, style, model
    )


def resolve_style_for_progress(progress: float) -> str:
    """根据 progress (0.0~1.0) 选择对应的风格模板。

    六段式分段方案，对齐 prosody curve 的语义渐变。
    """
    templates = MIMO_STYLE_TEMPLATES
    if not templates:
        return "用自然温柔的语调朗读"

    for segment in templates:
        low, high = segment["range"]
        if low <= progress < high or (high == 1.0 and progress == 1.0):
            return segment["style"]

    # fallback: 使用最后一段
    return templates[-1]["style"]


def map_inline_tag_to_audio_tag(tag_name: str) -> str | None:
    """将现有内联标记名映射为 MiMo 音频标签。

    Args:
        tag_name: 内联标记名（如 "慢速", "轻声", "极弱"）

    Returns:
        MiMo 音频标签字符串，或 None（不映射）
    """
    return MIMO_AUDIO_TAGS.get(tag_name)
