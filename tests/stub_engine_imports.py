"""在 import engine 之前注册桩模块，避免单测环境缺少 moviepy/edge_tts 等重依赖。"""
from __future__ import annotations

import sys
from types import ModuleType


def install() -> None:
    if getattr(install, "_done", False):
        return
    install._done = True  # type: ignore[attr-defined]

    def _mod(name: str) -> ModuleType:
        m = ModuleType(name)
        sys.modules[name] = m
        return m

    # PIL（engine 顶部会补 ANTIALIAS）
    pil = _mod("PIL")
    pil_image = _mod("PIL.Image")
    pil_image.LANCZOS = 1
    pil.Image = pil_image

    # edge_tts
    _mod("edge_tts")

    # numpy（仅保证 import；本文件单测不执行依赖 ndarray 形状的逻辑）
    np_mod = _mod("numpy")
    np_mod.zeros = lambda shape, dtype=None: [[0.0, 0.0]] * max(int(shape[0]), 1) if shape else []

    # yt_dlp
    _mod("yt_dlp")

    # openai（engine 在 import 时会实例化 OpenAI）
    openai = _mod("openai")

    class OpenAI:
        def __init__(self, *args, **kwargs):
            pass

    openai.OpenAI = OpenAI

    # moviepy
    _mod("moviepy")
    editor = _mod("moviepy.editor")

    def _dummy_cls(n: str):
        return type(n, (), {})

    for _n in (
        "ImageClip",
        "VideoFileClip",
        "AudioFileClip",
        "CompositeAudioClip",
        "CompositeVideoClip",
        "TextClip",
    ):
        setattr(editor, _n, _dummy_cls(_n))

    def _concat(*a, **k):
        return []

    editor.concatenate_videoclips = _concat
    editor.concatenate_audioclips = _concat

    _mod("moviepy.audio")
    aclip = _mod("moviepy.audio.AudioClip")

    class AudioArrayClip:
        pass

    aclip.AudioArrayClip = AudioArrayClip

    _mod("moviepy.audio.fx")
    fx_all = _mod("moviepy.audio.fx.all")
    fx_all.audio_loop = lambda *a, **k: None
    fx_all.audio_fadein = lambda *a, **k: None
    fx_all.audio_fadeout = lambda *a, **k: None

    _mod("moviepy.video")
    _mod("moviepy.video.fx")
    _mod("moviepy.video.fx.all")

    # rich
    rc = _mod("rich.console")

    class Console:
        def print(self, *a, **k):
            pass

    rc.Console = Console
    rp = _mod("rich.panel")

    class Panel:
        pass

    rp.Panel = Panel

    # dashscope（engine 会从 tts_v2 导入 SpeechSynthesizer；真单测里会 patch engine.SpeechSynthesizer）
    ds = _mod("dashscope")
    ds.api_key = ""
    ds.base_websocket_api_url = ""
    _mod("dashscope.audio")
    tts_v2 = _mod("dashscope.audio.tts_v2")

    class SpeechSynthesizer:
        def __init__(self, *a, **k):
            pass

        def call(self, text):
            return b""

    tts_v2.SpeechSynthesizer = SpeechSynthesizer


install()
