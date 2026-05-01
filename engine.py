# engine.py
"""统一入口 facade —— 委托到各功能模块。

所有公共函数保留在 engine 命名空间，现有调用者无需修改 import。
"""
# 必须放在最顶部的猴子补丁 (解决 Pillow 与 moviepy 版本冲突)
import PIL.Image
if not hasattr(PIL.Image, 'ANTIALIAS'):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS

# --- 故事生成 ---
from story_gen import (
    generate_story,
    generate_custom_theme,
    _evaluate_story,
    _generate_chapter_titles,
    _llm_call,
)

# --- 音频生成 ---
from audio_gen import (
    generate_audio,
    mix_final_audio,
    normalize_audio_loudness,
    generate_soothing_noise,
    _export_srt,
    _resolve_bgm_path,
)

# --- 视觉素材 ---
from visual_gen import (
    generate_and_crop_cover,
    apply_ken_burns,
    generate_ai_video,
    generate_multi_images,
    assemble_pro_video,
)

# --- BGM 管理 ---
from bgm import (
    download_bgm_from_youtube,
    select_best_bgm,
)

# --- 元数据与校验 ---
from metadata_gen import (
    generate_publish_metadata,
    validate_output,
)

# --- TTS 引擎（已拆分） ---
from tts_engine import TTSManager, CosyVoiceTTSEngine

# --- 保留向后兼容的别名 ---
def _synthesize_cosyvoice(text, output_path, speed=0.8):
    """向后兼容封装：用 CosyVoiceTTSEngine 实例调用。"""
    import asyncio
    engine = CosyVoiceTTSEngine()
    return asyncio.get_event_loop().run_until_complete(
        engine.synthesize(text, output_path, speed=speed)
    )
