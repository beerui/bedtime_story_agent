# tts_engine.py
"""TTS 引擎抽象层：统一接口 + 自动降级链。

引擎优先级: MiMo → CosyVoice → edge-tts
TTSManager 按优先级尝试，单句失败自动降级，额度耗尽全局切换。

用法:
    manager = TTSManager(theme_name="雨夜山中小屋")
    await manager.synthesize("你好世界", "out.mp3", speed=0.8, progress=0.5)
"""
import asyncio
import logging
import os
from abc import ABC, abstractmethod

import dashscope
import edge_tts
from dashscope.audio.tts_v2 import SpeechSynthesizer

from config import (
    API_CONFIG,
    EDGE_TTS_DEFAULT,
    MI_API_KEY,
    MIMO_PRESET_VOICES,
    THEME_MIMO_VOICE_MAP,
    THEME_VOICE_MAP,
)

logger = logging.getLogger(__name__)


class BaseTTSEngine(ABC):
    """TTS 引擎抽象基类。"""

    name: str = "base"

    @abstractmethod
    async def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 0.8,
        voice: str | None = None,
        progress: float = 0.0,
        prosody_tag: str | None = None,
    ) -> bool:
        """合成语音到文件。成功返回 True，失败返回 False（不抛异常）。

        Args:
            prosody_tag: 内联韵律标记名（如 "慢速", "轻声", "极弱"），
                         供 MiMo 引擎转换为音频标签。其他引擎忽略。
        """

    @abstractmethod
    def is_available(self) -> bool:
        """引擎当前是否可用（配置完整、额度未耗尽等）。"""


class MiMoTTSEngine(BaseTTSEngine):
    """MiMo TTS 引擎：封装 mimo_tts.py。"""

    name = "mimo"

    def __init__(self, theme_name: str | None = None):
        self._theme_name = theme_name
        self._disabled = False

    def is_available(self) -> bool:
        if self._disabled:
            return False
        if not MI_API_KEY:
            return False
        engine = API_CONFIG.get("tts_engine", "cosyvoice")
        return engine == "mimo"

    def disable(self, reason: str = ""):
        """禁用 MiMo 引擎（额度耗尽等场景），与 CosyVoiceTTSEngine 对称。"""
        self._disabled = True
        logger.warning("MiMo TTS 已禁用: %s", reason)

    async def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 0.8,
        voice: str | None = None,
        progress: float = 0.0,
        prosody_tag: str | None = None,
    ) -> bool:
        from mimo_tts import synthesize_mimo, resolve_style_for_progress, map_inline_tag_to_audio_tag

        voice = voice or self._resolve_voice()
        style = resolve_style_for_progress(progress)

        # 将内联韵律标记转换为 MiMo 音频标签，前置到文本
        audio_tag = map_inline_tag_to_audio_tag(prosody_tag) if prosody_tag else None
        if audio_tag:
            text = f"({audio_tag}){text}"

        return await asyncio.to_thread(
            synthesize_mimo, text, output_path, voice=voice, style=style, speed=speed
        )

    def _resolve_voice(self) -> str:
        if self._theme_name:
            mapped = THEME_MIMO_VOICE_MAP.get(self._theme_name)
            if mapped:
                return mapped
        return "冰糖"


class CosyVoiceTTSEngine(BaseTTSEngine):
    """CosyVoice 引擎：封装 DashScope SDK。"""

    name = "cosyvoice"

    def __init__(self):
        self._disabled = False

    def is_available(self) -> bool:
        if self._disabled:
            return False
        return bool(API_CONFIG.get("cosyvoice_api_key", "").strip())

    def disable(self, reason: str = ""):
        self._disabled = True
        logger.warning("CosyVoice 已禁用: %s", reason)

    async def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 0.8,
        voice: str | None = None,
        progress: float = 0.0,
        prosody_tag: str | None = None,
    ) -> bool:
        dashscope.api_key = API_CONFIG.get("cosyvoice_api_key", "")
        voice = voice or API_CONFIG.get("tts_voice", "longxiaochun")
        model = _cosyvoice_model_for_voice(voice)

        def run_sdk():
            synthesizer = SpeechSynthesizer(
                model=model, voice=voice, speech_rate=speed
            )
            audio_data = synthesizer.call(text)
            if not audio_data:
                raise Exception("CosyVoice 返回了空的音频数据")
            with open(output_path, "wb") as f:
                f.write(audio_data)

        try:
            await asyncio.to_thread(run_sdk)
            return True
        except Exception as e:
            err_str = str(e)
            if "AllocationQuota" in err_str or "FreeTierOnly" in err_str:
                self.disable(f"额度耗尽: {err_str}")
            raise


class EdgeTTSEngine(BaseTTSEngine):
    """edge-tts 引擎：免费兜底。"""

    name = "edge-tts"

    def __init__(self, theme_name: str | None = None):
        self._theme_name = theme_name

    def is_available(self) -> bool:
        return True  # edge-tts 始终可用

    async def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 0.8,
        voice: str | None = None,
        progress: float = 0.0,
        prosody_tag: str | None = None,
    ) -> bool:
        voice = voice or self._resolve_voice()
        edge_rate = f"{int((speed - 1.0) * 100):+d}%"
        try:
            await edge_tts.Communicate(text, voice, rate=edge_rate).save(output_path)
            return True
        except Exception as e:
            logger.error("edge-tts 合成失败: %s", e)
            return False

    def _resolve_voice(self) -> str:
        if self._theme_name:
            return THEME_VOICE_MAP.get(self._theme_name, EDGE_TTS_DEFAULT)
        return EDGE_TTS_DEFAULT


def _cosyvoice_model_for_voice(voice_name: str) -> str:
    """音色与 CosyVoice 模型须同代，否则 API 418。"""
    vn = (voice_name or "").lower()
    if vn.startswith("http://") or vn.startswith("https://"):
        return "cosyvoice-clone-v1"
    if "v2" in vn:
        return "cosyvoice-v2"
    if vn == "longanyang" or "_v3" in vn or vn.endswith("v3") or "v3" in vn:
        return "cosyvoice-v3-flash"
    return "cosyvoice-v1"


class TTSManager:
    """TTS 管理器：按优先级尝试引擎，自动降级。

    Args:
        theme_name: 当前主题名，用于自动选择音色。
        engine_order: 引擎优先级顺序。默认 MiMo → CosyVoice → edge-tts。
    """

    def __init__(
        self,
        theme_name: str | None = None,
        engine_order: list[str] | None = None,
    ):
        self._engines: dict[str, BaseTTSEngine] = {
            "mimo": MiMoTTSEngine(theme_name),
            "cosyvoice": CosyVoiceTTSEngine(),
            "edge-tts": EdgeTTSEngine(theme_name),
        }
        self._order = engine_order or ["mimo", "cosyvoice", "edge-tts"]

    async def synthesize(
        self,
        text: str,
        output_path: str,
        speed: float = 0.8,
        progress: float = 0.0,
        prosody_tag: str | None = None,
    ) -> bool:
        """尝试所有可用引擎，成功返回 True，全部失败返回 False。"""
        for name in self._order:
            engine = self._engines[name]
            if not engine.is_available():
                continue
            try:
                ok = await engine.synthesize(
                    text, output_path, speed=speed, progress=progress,
                    prosody_tag=prosody_tag,
                )
                if ok:
                    return True
                logger.warning("%s 返回 False，尝试下一个引擎", name)
            except Exception as e:
                logger.warning("%s 合成异常: %s，尝试下一个引擎", name, e)
                continue
        logger.error("所有 TTS 引擎均失败: %s", text[:30])
        return False

    def get_cosyvoice_engine(self) -> CosyVoiceTTSEngine:
        """获取 CosyVoice 引擎实例（供外部检查禁用状态）。"""
        return self._engines["cosyvoice"]
