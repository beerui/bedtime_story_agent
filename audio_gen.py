# audio_gen.py
"""音频生成引擎：TTS 合成、混音、响度归一化、底噪生成。"""
import asyncio
import os
import re

import numpy as np
from moviepy.editor import (
    AudioFileClip,
    CompositeAudioClip,
    concatenate_audioclips,
)
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.audio.fx.all import audio_loop, audio_fadein, audio_fadeout
from rich.console import Console

from config import PROSODY_CURVES, CURRENT_PROSODY_CURVE
from prosody import (
    ProsodyCurve,
    apply_curve_to_blocks,
    parse_silence,
    parse_phase_marker,
    TAG_MULTIPLIERS,
)
from tts_engine import TTSManager

console = Console()


def _resolve_bgm_path(bgm_filename: str) -> str | None:
    """查找 BGM 文件路径，优先 assets/bgm/，回退 assets/。"""
    if not bgm_filename:
        return None
    for candidate in (f"assets/bgm/{bgm_filename}", f"assets/{bgm_filename}"):
        if os.path.exists(candidate):
            return candidate
    return None


async def generate_audio(text: str, output_dir: str, theme_name: str | None = None):
    """主音频生成流水线：词法解析 → 区块组装 → 韵律应用 → TTS 合成 → 拼接 → 字幕。"""
    voice_path = os.path.join(output_dir, "voice.mp3")
    console.print("\n[bold cyan][音频车间] 韵律弧线引擎启动 (Prosody Curve + 物理混音)...[/bold cyan]")

    curve = ProsodyCurve(PROSODY_CURVES[CURRENT_PROSODY_CURVE])

    # 1. 词法解析
    tokens = []
    prev_was_newlines = False
    for m in re.finditer(r"(\[.*?\]|【.*?】|\(.*?\)|（.*?）)|([^\[\]【】()（）]+)", text):
        tag = m.group(1)
        txt = m.group(2)
        if tag:
            t = tag.strip()
            phase = parse_phase_marker(t)
            if phase:
                tokens.append({"type": "phase_marker", "phase": phase, "raw": tag})
                continue
            tag_name = t.strip("[]【】")
            if tag_name in TAG_MULTIPLIERS:
                tokens.append({"type": "prosody", "tag": tag_name, "raw": tag})
                continue
            sec = parse_silence(t)
            if sec is not None:
                tokens.append({"type": "break", "sec": sec, "raw": tag})
        elif txt:
            if "\n\n" in txt:
                prev_was_newlines = True
            sub_sentences = re.split(r"([。！？!?\n]+)", txt)
            for j in range(0, len(sub_sentences) - 1, 2):
                sent = sub_sentences[j] + sub_sentences[j + 1]
                if sent.strip():
                    tok = {"type": "text", "text": sent.strip()}
                    if prev_was_newlines:
                        tok["paragraph_start"] = True
                        prev_was_newlines = False
                    tokens.append(tok)
            if len(sub_sentences) % 2 != 0 and sub_sentences[-1].strip():
                tok = {"type": "text", "text": sub_sentences[-1].strip()}
                if prev_was_newlines:
                    tok["paragraph_start"] = True
                    prev_was_newlines = False
                tokens.append(tok)

    # 2. 组装区块
    blocks = []
    pending_multiplier = None
    for token in tokens:
        if token["type"] == "phase_marker":
            blocks.append({"type": "phase_marker", "phase": token["phase"]})
        elif token["type"] == "prosody":
            pending_multiplier = TAG_MULTIPLIERS[token["tag"]]
        elif token["type"] == "break":
            blocks.append({"type": "pure_break", "sec": token["sec"], "raw": token["raw"]})
        elif token["type"] == "text":
            clean = token["text"].replace("**", "").replace("*", "").replace("---", "").strip()
            if re.search(r"[一-龥a-zA-Z0-9]", clean):
                block = {"type": "speech", "text": clean}
                if pending_multiplier:
                    block["multiplier"] = pending_multiplier
                    pending_multiplier = None
                if token.get("paragraph_start"):
                    block["paragraph_start"] = True
                blocks.append(block)

    # 3. 应用韵律弧线
    blocks = apply_curve_to_blocks(blocks, curve)

    # 4. 合成与拼接
    audio_clips, temp_files, subtitles_info = [], [], []
    current_time = 0.0
    tts_manager = TTSManager(theme_name=theme_name)

    for i, block in enumerate(blocks):
        if block["type"] in ("pure_break", "auto_pause"):
            sec = block["sec"]
            label = "弧线停顿" if block["type"] == "auto_pause" else f"留白: '{block.get('raw', '')}'"
            console.print(f"  [dim]  {label} ({sec:.2f}s)[/dim]")
            sr = 44100
            audio_clips.append(AudioArrayClip(np.zeros((int(sr * sec), 2)), fps=sr))
            current_time += sec
            continue

        if block["type"] != "speech":
            continue

        sub_text_clean = block["text"]
        speed = block.get("speed", 0.8)
        vol = block.get("vol", 1.0)
        progress = block.get("progress", 0.0)

        console.print(f"  [速:{speed:.2f}, 音:{vol:.2f}, 进度:{progress:.0%}]: {sub_text_clean[:18]}...")
        temp_path = os.path.join(output_dir, f"temp_voice_{i}.mp3")

        try:
            ok = await tts_manager.synthesize(
                sub_text_clean, temp_path, speed=speed, progress=progress
            )
            if not ok:
                console.print(f"[red]  语音合成失败，跳过该句[/red]")
                continue
        except Exception as e:
            console.print(f"[red]  语音合成失败，跳过该句: {e}[/red]")
            continue

        try:
            clip = AudioFileClip(temp_path)
            if vol < 1.0:
                clip = clip.volumex(vol)
            fade_in_time = min(0.05 + 0.15 * progress, clip.duration / 3)
            fade_out_time = min(0.2 + 0.6 * progress, clip.duration / 3)
            clip = clip.fx(audio_fadein, fade_in_time).fx(audio_fadeout, fade_out_time)
            audio_clips.append(clip)
            temp_files.append(temp_path)
            subtitles_info.append({"text": sub_text_clean, "start": current_time, "duration": clip.duration})
            current_time += clip.duration
        except Exception as e:
            console.print(f"[red]  读取音频片段失败: {e}[/red]")
            continue

    if not audio_clips:
        console.print("[bold red]严重错误：剧本中没有提取到任何有效语音！[/bold red]")
        return None, []

    console.print("  -> 正在拼接音频时间轴...")
    final_audio = concatenate_audioclips(audio_clips)
    final_audio.write_audiofile(voice_path, logger=None)

    for c in audio_clips:
        c.close()
    for tf in temp_files:
        try:
            os.remove(tf)
        except OSError:
            pass

    if subtitles_info:
        _export_srt(subtitles_info, os.path.join(output_dir, "subtitles.srt"))

    return voice_path, subtitles_info


def _export_srt(subtitles_info: list[dict], srt_path: str):
    """将 subtitles_info 导出为标准 SRT 字幕文件。"""

    def _fmt_ts(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for i, sub in enumerate(subtitles_info, 1):
        start = sub["start"]
        end = start + sub["duration"]
        text = sub["text"].strip()
        lines.append(f"{i}")
        lines.append(f"{_fmt_ts(start)} --> {_fmt_ts(end)}")
        lines.append(text)
        lines.append("")

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    console.print(f"  [dim]字幕: {srt_path} ({len(subtitles_info)} 条)[/dim]")


def generate_soothing_noise(output_path: str, duration: int = 60, color: str = "brown") -> str:
    """生成环境底噪（棕噪/粉噪/白噪）。"""
    sr = 44100
    n_samples = int(sr * duration)
    rng = np.random.default_rng()

    if color == "brown":
        white = rng.standard_normal(n_samples)
        brown = np.cumsum(white)
        t = np.arange(n_samples)
        slope = (brown[-1] - brown[0]) / max(1, n_samples - 1)
        brown = brown - slope * t
        brown = brown - brown.mean()
        signal = brown
    elif color == "pink":
        white = rng.standard_normal(n_samples)
        spec = np.fft.rfft(white)
        freqs = np.fft.rfftfreq(n_samples, d=1 / sr)
        freqs[0] = 1
        spec = spec / np.sqrt(freqs)
        signal = np.fft.irfft(spec, n=n_samples)
    else:
        signal = rng.uniform(-1, 1, n_samples)

    peak = np.max(np.abs(signal))
    if peak > 0:
        signal = signal / peak * 0.9

    fade_samples = int(sr * 2)
    fade_samples = min(fade_samples, n_samples // 2)
    if fade_samples > 0:
        fade_in = np.linspace(0, 1, fade_samples)
        fade_out = np.linspace(1, 0, fade_samples)
        signal[:fade_samples] *= fade_in
        signal[-fade_samples:] *= fade_out

    clip = AudioArrayClip(np.vstack((signal, signal)).T, fps=sr)
    clip.write_audiofile(output_path, fps=sr, logger=None)
    return output_path


def mix_final_audio(
    voice_path: str,
    bgm_filename: str | None,
    output_dir: str,
    fade_in: int = 5,
    fade_out: int = 10,
    bgm_vol: float = 0.25,
) -> str:
    """将配音和 BGM 混合为成品音频。"""
    final_path = os.path.join(output_dir, "final_audio.mp3")
    if os.path.exists(final_path):
        console.print(f"[dim]  成品音频已存在，跳过混音: {final_path}[/dim]")
        return final_path

    console.print("\n[bold cyan][混音车间] 正在合成成品音频...[/bold cyan]")
    voice_clip = AudioFileClip(voice_path)
    total_dur = voice_clip.duration + 4

    bgm_path = _resolve_bgm_path(bgm_filename)
    if bgm_path:
        bgm_clip = AudioFileClip(bgm_path)
        console.print(f"  BGM: {bgm_path}")
    else:
        noise_path = "assets/auto_generated_noise.mp3"
        if not os.path.exists(noise_path):
            generate_soothing_noise(noise_path, 60)
        bgm_clip = AudioFileClip(noise_path)
        console.print(f"  BGM: 自动生成棕噪底噪（配置 {bgm_filename or '未指定'} 不存在）")

    looped_bgm = audio_loop(bgm_clip, duration=total_dur)
    looped_bgm = looped_bgm.volumex(bgm_vol)
    looped_bgm = looped_bgm.fx(audio_fadein, fade_in).fx(audio_fadeout, fade_out)

    final_audio = CompositeAudioClip([looped_bgm, voice_clip.set_start(2)])
    final_audio.fps = voice_clip.fps or 44100
    final_audio.write_audiofile(final_path, logger=None)

    voice_clip.close()
    bgm_clip.close()

    # LUFS 归一化
    try:
        import audio_fx

        if audio_fx.available():
            target = float(os.getenv("NORMALIZE_LUFS", str(audio_fx.DEFAULT_TARGET_LUFS)))
            before = audio_fx.measure_lufs(final_path)
            if audio_fx.normalize_mp3(final_path, target_lufs=target):
                after = audio_fx.measure_lufs(final_path)
                if before is not None and after is not None:
                    console.print(f"  响度归一: {before:.1f} → {after:.1f} LUFS (目标 {target})")
    except Exception as _lufs_err:
        console.print(f"  [yellow]响度归一跳过（忽略）: {_lufs_err}[/yellow]")

    size_mb = os.path.getsize(final_path) / 1024 / 1024
    console.print(f"  [green]成品音频: {final_path} ({size_mb:.1f}MB)[/green]")
    return final_path


def normalize_audio_loudness(audio_path: str, target_lufs: float = -16.0):
    """简易响度归一化。"""
    try:
        clip = AudioFileClip(audio_path)
        fps = clip.fps or 44100
        samples = clip.to_soundarray(fps=fps)
        rms = np.sqrt(np.mean(samples**2))
        if rms < 1e-8:
            clip.close()
            return
        target_rms = 10 ** (target_lufs / 20.0)
        gain = target_rms / rms
        gain = max(0.3, min(3.0, gain))
        if abs(gain - 1.0) < 0.05:
            clip.close()
            console.print(f"  [dim]响度已在目标范围，无需调整[/dim]")
            return
        console.print(f"  响度归一化: gain={gain:.2f}x")
        normalized = clip.volumex(gain)
        normalized.write_audiofile(audio_path, logger=None)
        clip.close()
        normalized.close()
    except Exception as e:
        console.print(f"  [yellow]响度归一化跳过: {e}[/yellow]")
