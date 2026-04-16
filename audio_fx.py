#!/usr/bin/env python3
"""LUFS 响度归一：把每期音频统一到助眠友好的 -22 LUFS，避免跨期音量突变。

用的是 ffmpeg 的 loudnorm 滤镜——EBU R128 实现，业界标准。只做线性增益调整，
不压缩动态范围（韵律弧线的渐弱效果保留）。

用法:
    from audio_fx import normalize_mp3
    normalize_mp3('outputs/Batch_xxx/final_audio.mp3', target_lufs=-22)
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional

# 睡前音频响度目标。业界对比参照：
#   -16 LUFS  podcast 标准（通勤/日间，较响）
#   -19 LUFS  沉浸式 podcast（Serial, Radiolab 级制作）
#   -22 LUFS  我们的默认——助眠友好，睡前音量合适但清晰可辨
#   -24 LUFS  冥想音频下限（偏安静）
DEFAULT_TARGET_LUFS = -22.0


def _find_ffmpeg() -> Optional[str]:
    """定位 ffmpeg：优先系统 PATH，其次 moviepy/imageio_ffmpeg 绑定的版本。"""
    p = shutil.which("ffmpeg")
    if p:
        return p
    # Fall back to imageio-ffmpeg's bundled binary (moviepy's dep)
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _has_ffmpeg() -> bool:
    return _find_ffmpeg() is not None


def available() -> bool:
    """ffmpeg 是否可用（唯一硬依赖）"""
    return _has_ffmpeg()


def measure_lufs(mp3_path: str | Path) -> Optional[float]:
    """返回音频的 integrated LUFS；失败返回 None。
    优先用 pyloudnorm（更精确），没装则用 ffmpeg 的 ebur128。"""
    path = Path(mp3_path)
    if not path.is_file():
        return None
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    # Try pyloudnorm (decodes via ffmpeg → WAV in memory)
    try:
        import soundfile as sf
        import pyloudnorm as pyln
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-loglevel", "error", "-i", str(path),
             "-f", "wav", "-ac", "1", "-"],
            capture_output=True, check=True,
        )
        import io
        data, sr = sf.read(io.BytesIO(proc.stdout))
        if len(data) < 1024:
            return None
        meter = pyln.Meter(sr)
        return float(meter.integrated_loudness(data))
    except ImportError:
        pass
    except Exception:
        return None
    # Fallback: ffmpeg ebur128 filter parse
    try:
        proc = subprocess.run(
            [ffmpeg, "-nostdin", "-i", str(path),
             "-af", "ebur128=peak=true", "-f", "null", "-"],
            capture_output=True, text=True, timeout=120,
        )
        for line in proc.stderr.splitlines():
            line = line.strip()
            if line.startswith("I:") and "LUFS" in line:
                parts = line.replace("I:", "").replace("LUFS", "").split()
                if parts:
                    return float(parts[0])
    except Exception:
        return None
    return None


def normalize_mp3(
    mp3_path: str | Path,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak: float = -1.5,
    loudness_range: float = 11.0,
    bitrate: str = "128k",
) -> bool:
    """用 ffmpeg loudnorm 滤镜原地归一。返回是否成功。

    用两遍法：第一遍测量现有 LUFS/LRA/TP，第二遍用测量结果做动态归一。
    比单遍线性归一更接近目标——对已经很安静的源（如助眠音频）尤其重要。"""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return False

    src = Path(mp3_path)
    if not src.is_file():
        return False

    # Pass 1: measure
    af1 = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={loudness_range}:print_format=json"
    try:
        proc1 = subprocess.run(
            [ffmpeg, "-nostdin", "-i", str(src), "-af", af1, "-f", "null", "-"],
            capture_output=True, text=True, timeout=300,
        )
        # ffmpeg prints the JSON block to stderr. Extract the `{...}` substring.
        stderr = proc1.stderr
        import json
        start = stderr.rfind("{")
        end = stderr.rfind("}")
        measured: dict = {}
        if start >= 0 and end > start:
            try:
                measured = json.loads(stderr[start:end + 1])
            except Exception:
                measured = {}
    except Exception:
        measured = {}

    tmp = src.with_suffix(".normalized.mp3")
    if measured:
        af2 = (
            f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={loudness_range}"
            f":measured_I={measured.get('input_i', 0)}"
            f":measured_TP={measured.get('input_tp', 0)}"
            f":measured_LRA={measured.get('input_lra', 0)}"
            f":measured_thresh={measured.get('input_thresh', 0)}"
            f":offset={measured.get('target_offset', 0)}"
            f":linear=true"
        )
    else:
        # Fall back to single-pass (limited effectiveness on quiet sources)
        af2 = f"loudnorm=I={target_lufs}:TP={true_peak}:LRA={loudness_range}"

    try:
        proc = subprocess.run(
            [
                ffmpeg, "-nostdin", "-y", "-loglevel", "error",
                "-i", str(src),
                "-af", af2,
                "-c:a", "libmp3lame", "-b:a", bitrate,
                str(tmp),
            ],
            capture_output=True, text=True, timeout=300,
        )
        if proc.returncode != 0:
            tmp.unlink(missing_ok=True)
            return False
        tmp.replace(src)
        return True
    except Exception:
        tmp.unlink(missing_ok=True)
        return False


if __name__ == "__main__":
    # CLI smoke test
    import sys
    if len(sys.argv) < 2:
        print("用法: python3 audio_fx.py <mp3_path> [target_lufs]", file=sys.stderr)
        sys.exit(1)
    path = sys.argv[1]
    target = float(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_TARGET_LUFS
    before = measure_lufs(path)
    if before is not None:
        print(f"before: {before:.1f} LUFS")
    ok = normalize_mp3(path, target_lufs=target)
    if not ok:
        print("normalize failed", file=sys.stderr)
        sys.exit(2)
    after = measure_lufs(path)
    if after is not None:
        print(f"after:  {after:.1f} LUFS (target {target})")
