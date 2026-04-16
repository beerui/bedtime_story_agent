#!/usr/bin/env python3
"""双耳节拍（Binaural Beats）生成与混音工具。

科学原理：左右耳播放略有频差的纯音，大脑感知差频处的"节拍"。
  - Alpha (8-12 Hz): 放松、冥想
  - Theta (4-8 Hz):  浅睡、入梦
  - Delta (0.5-4 Hz): 深度睡眠

本模块生成从 Alpha 渐变到 Delta 的双耳节拍音轨，可叠加到任何
已有音频上，增强助眠效果。

用法:
    # 增强现有音频（生成 *_binaural.mp3 到同目录）
    python3 binaural.py outputs/Batch_20260415_082326_午夜慢车/final_audio.mp3

    # 批量增强所有已生产内容
    python3 binaural.py --all

    # 仅生成独立的双耳节拍音轨（5 分钟）
    python3 binaural.py --standalone --duration 300 -o binaural_track.mp3

    # 自定义载波频率和音量
    python3 binaural.py final_audio.mp3 --carrier 180 --volume 0.08
"""
import argparse
import os
import struct
import sys
import wave
import math
import tempfile
from pathlib import Path

import numpy as np

# ---------------------------------------------------------------------------
# Binaural beat synthesis
# ---------------------------------------------------------------------------

# 频段定义 (name, beat_freq_hz)
BANDS = {
    "alpha": 10.0,   # 放松
    "theta": 6.0,    # 浅睡
    "delta": 2.0,    # 深睡
}

# 默认渐变时间线: (progress_0_to_1, beat_freq_hz)
# Alpha → Theta → Delta，模拟自然入睡过程
DEFAULT_CURVE = [
    (0.00, 10.0),   # 开始：Alpha 放松
    (0.15,  8.0),   # 过渡到 Theta
    (0.40,  5.0),   # 深度 Theta
    (0.70,  3.0),   # 进入 Delta
    (1.00,  1.5),   # 深度 Delta
]


def _lerp_curve(curve: list[tuple[float, float]], t: float) -> float:
    """Piecewise-linear interpolation on a (progress, value) curve."""
    if t <= curve[0][0]:
        return curve[0][1]
    if t >= curve[-1][0]:
        return curve[-1][1]
    for i in range(len(curve) - 1):
        t0, v0 = curve[i]
        t1, v1 = curve[i + 1]
        if t0 <= t <= t1:
            ratio = (t - t0) / (t1 - t0) if t1 != t0 else 0
            return v0 + (v1 - v0) * ratio
    return curve[-1][1]


def generate_binaural(
    duration_sec: float,
    sample_rate: int = 44100,
    carrier_hz: float = 150.0,
    volume: float = 0.10,
    curve: list[tuple[float, float]] | None = None,
) -> np.ndarray:
    """Generate stereo binaural beat audio as numpy array.

    Returns shape (num_samples, 2), values in [-1, 1].

    Args:
        duration_sec: Total duration in seconds.
        sample_rate: Audio sample rate.
        carrier_hz: Base carrier frequency (both ears share this base).
        volume: Peak amplitude (0-1). Keep low (~0.08-0.12) for subtlety.
        curve: Beat frequency curve as [(progress, hz), ...].
               Defaults to Alpha→Delta transition.
    """
    if curve is None:
        curve = DEFAULT_CURVE

    n_samples = int(duration_sec * sample_rate)
    t = np.arange(n_samples, dtype=np.float64) / sample_rate
    progress = np.linspace(0, 1, n_samples)

    # compute time-varying beat frequency
    beat_freq = np.array([_lerp_curve(curve, p) for p in progress])

    # phase accumulation for smooth frequency transitions
    left_phase = 2 * np.pi * carrier_hz * t
    # right ear: carrier + beat/2, left ear: carrier - beat/2
    # This centers the perceived beat on the carrier frequency
    half_beat_phase = np.cumsum(beat_freq / sample_rate) * np.pi
    left = np.sin(left_phase - half_beat_phase)
    right = np.sin(left_phase + half_beat_phase)

    # gentle volume envelope: fade in 10s, fade out 15s
    fade_in_samples = min(int(10 * sample_rate), n_samples // 4)
    fade_out_samples = min(int(15 * sample_rate), n_samples // 3)
    envelope = np.ones(n_samples)
    if fade_in_samples > 0:
        envelope[:fade_in_samples] = np.linspace(0, 1, fade_in_samples)
    if fade_out_samples > 0:
        envelope[-fade_out_samples:] = np.linspace(1, 0, fade_out_samples)

    left = left * volume * envelope
    right = right * volume * envelope

    stereo = np.column_stack([left, right]).astype(np.float32)
    return stereo


def write_wav(samples: np.ndarray, path: str, sample_rate: int = 44100):
    """Write float32 stereo samples to a WAV file."""
    int16_samples = (np.clip(samples, -1, 1) * 32767).astype(np.int16)
    with wave.open(path, "w") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(int16_samples.tobytes())


# ---------------------------------------------------------------------------
# Mix binaural beats into existing audio
# ---------------------------------------------------------------------------

def enhance_audio(input_path: str, output_path: str | None = None,
                  carrier_hz: float = 150.0, volume: float = 0.10) -> str:
    """Add binaural beats to an existing audio file.

    Uses moviepy (already a project dependency) for audio I/O.
    Returns path to the enhanced file.
    """
    from moviepy.editor import AudioFileClip, CompositeAudioClip
    from moviepy.audio.AudioClip import AudioArrayClip

    if output_path is None:
        p = Path(input_path)
        output_path = str(p.with_stem(p.stem + "_binaural"))

    clip = AudioFileClip(input_path)
    sr = clip.fps or 44100
    duration = clip.duration

    # generate binaural layer
    binaural = generate_binaural(
        duration_sec=duration,
        sample_rate=sr,
        carrier_hz=carrier_hz,
        volume=volume,
    )

    binaural_clip = AudioArrayClip(binaural, fps=sr)
    mixed = CompositeAudioClip([clip, binaural_clip])
    mixed.duration = duration
    mixed.fps = sr
    mixed.write_audiofile(output_path, logger=None)

    clip.close()
    binaural_clip.close()

    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="双耳节拍生成器——为助眠音频注入科学催眠音轨",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 binaural.py final_audio.mp3             # 增强单个文件
  python3 binaural.py --all                        # 增强所有已生产内容
  python3 binaural.py --standalone -o beats.wav    # 仅生成节拍音轨
        """,
    )
    parser.add_argument("input", nargs="?", help="要增强的音频文件路径")
    parser.add_argument("--all", action="store_true", help="增强 outputs/ 中所有 final_audio.mp3")
    parser.add_argument("--standalone", action="store_true", help="仅生成独立双耳节拍音轨")
    parser.add_argument("--duration", type=int, default=300, help="独立音轨时长（秒，默认 300）")
    parser.add_argument("--carrier", type=float, default=150.0, help="载波频率 Hz（默认 150）")
    parser.add_argument("--volume", type=float, default=0.10, help="节拍音量 0-1（默认 0.10）")
    parser.add_argument("-o", "--output", help="输出文件路径")
    args = parser.parse_args()

    try:
        from rich.console import Console
        console = Console()
        def info(msg): console.print(msg)
    except ImportError:
        def info(msg): print(msg)

    if args.standalone:
        # 生成独立音轨
        out = args.output or "binaural_track.wav"
        info(f"[cyan]生成 {args.duration}s 双耳节拍音轨...[/cyan]")
        info(f"  载波: {args.carrier} Hz | 音量: {args.volume}")
        info(f"  频段: Alpha(10Hz) → Theta(6Hz) → Delta(1.5Hz)")
        samples = generate_binaural(
            duration_sec=args.duration,
            carrier_hz=args.carrier,
            volume=args.volume,
        )
        write_wav(samples, out)
        size_kb = os.path.getsize(out) / 1024
        info(f"  [green]已保存: {out} ({size_kb:.0f}KB)[/green]")
        return

    if args.all:
        # 批量增强
        outputs_dir = Path(__file__).parent / "outputs"
        if not outputs_dir.is_dir():
            info("[red]outputs/ 目录不存在[/red]")
            return
        targets = sorted(outputs_dir.glob("*/final_audio.mp3"))
        if not targets:
            info("[yellow]没有找到 final_audio.mp3 文件[/yellow]")
            return
        info(f"[cyan]批量增强 {len(targets)} 个音频...[/cyan]")
        for audio in targets:
            binaural_path = audio.with_stem("final_audio_binaural")
            if binaural_path.exists():
                info(f"  [dim]已存在，跳过: {binaural_path.name} ({audio.parent.name})[/dim]")
                continue
            info(f"  增强: {audio.parent.name}")
            enhance_audio(
                str(audio), str(binaural_path),
                carrier_hz=args.carrier, volume=args.volume,
            )
            size_mb = binaural_path.stat().st_size / 1024 / 1024
            info(f"    [green]→ {binaural_path.name} ({size_mb:.1f}MB)[/green]")
        info("[bold green]批量增强完成[/bold green]")
        return

    if not args.input:
        parser.print_help()
        return

    if not os.path.isfile(args.input):
        info(f"[red]文件不存在: {args.input}[/red]")
        return

    info(f"[cyan]增强: {args.input}[/cyan]")
    info(f"  载波: {args.carrier} Hz | 节拍音量: {args.volume}")
    info(f"  Alpha(10Hz) → Theta(6Hz) → Delta(1.5Hz)")
    result = enhance_audio(
        args.input, args.output,
        carrier_hz=args.carrier, volume=args.volume,
    )
    size_mb = os.path.getsize(result) / 1024 / 1024
    info(f"  [green]已保存: {result} ({size_mb:.1f}MB)[/green]")


if __name__ == "__main__":
    main()
