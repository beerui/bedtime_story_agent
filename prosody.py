# prosody.py
"""全局韵律弧线引擎：将稿件进度映射为 speed/volume/pause 曲线。"""
import re


class ProsodyCurve:
    """分段线性韵律曲线，从 config.PROSODY_CURVES 的控制点插值。"""

    def __init__(self, curve_config: dict):
        self._speed = curve_config["speed"]
        self._volume = curve_config["volume"]
        self._pause = curve_config["pause"]

    @staticmethod
    def _lerp(points: list[tuple[float, float]], t: float) -> float:
        t = max(0.0, min(1.0, t))
        if t <= points[0][0]:
            return points[0][1]
        if t >= points[-1][0]:
            return points[-1][1]
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            if x0 <= t <= x1:
                ratio = (t - x0) / (x1 - x0) if x1 != x0 else 0.0
                return y0 + (y1 - y0) * ratio
        return points[-1][1]

    def interpolate(self, progress: float) -> tuple[float, float, float]:
        return (
            self._lerp(self._speed, progress),
            self._lerp(self._volume, progress),
            self._lerp(self._pause, progress),
        )


# 阶段标记到曲线锚点的映射
PHASE_ANCHORS = {
    "引入": 0.0,
    "深入": 0.3,
    "尾声": 0.7,
}

# 内联标记的乘法系数
TAG_MULTIPLIERS = {
    "慢速": {"speed": 0.8, "volume": 1.0},
    "轻声": {"speed": 1.0, "volume": 0.5},
    "极弱": {"speed": 0.7, "volume": 0.3},
}


def parse_silence(tag: str) -> float | None:
    """统一解析停顿/环境音标记，返回静音秒数。非此类标记返回 None。"""
    p = tag.strip()
    if re.match(r"^[\[【]环境音[^\]】]*[\]】]$", p):
        return 4.0
    if p in ("[停顿]", "【停顿】"):
        return 0.8
    m = re.match(r"^[\[【]停顿\s*(\d+)\s*ms[\]】]$", p)
    if m:
        return max(0.05, min(10.0, int(m.group(1)) / 1000.0))
    m = re.match(r"^[\[【]停顿\s*(\d+(?:\.\d+)?)\s*s[\]】]$", p)
    if m:
        return max(0.05, min(10.0, float(m.group(1))))
    return None


def parse_phase_marker(tag: str) -> str | None:
    """解析 [阶段：XXX]，返回阶段名或 None。"""
    m = re.match(r"^[\[【]阶段[：:](.+?)[\]】]$", tag.strip())
    return m.group(1).strip() if m else None


def _build_progress_map(blocks: list[dict]) -> list[float]:
    """为每个 speech block 计算曲线进度值，考虑阶段标记。"""
    speech_indices = []
    phase_marks = []  # (speech_block_order, anchor_progress)

    speech_count = 0
    for b in blocks:
        if b["type"] == "speech":
            speech_indices.append(speech_count)
            speech_count += 1
        elif b["type"] == "phase_marker":
            anchor = PHASE_ANCHORS.get(b.get("phase", ""))
            if anchor is not None:
                phase_marks.append((speech_count, anchor))

    if speech_count == 0:
        return []

    if not phase_marks:
        return [i / max(speech_count - 1, 1) for i in range(speech_count)]

    # 用阶段锚点重映射进度
    anchors = [(0, 0.0)] + phase_marks + [(speech_count, 1.0)]
    # 去重、排序
    seen = set()
    unique = []
    for idx, prog in anchors:
        if idx not in seen:
            seen.add(idx)
            unique.append((idx, prog))
    unique.sort()

    progress_map = [0.0] * speech_count
    for seg in range(len(unique) - 1):
        start_idx, start_prog = unique[seg]
        end_idx, end_prog = unique[seg + 1]
        span = end_idx - start_idx
        for i in range(start_idx, min(end_idx, speech_count)):
            ratio = (i - start_idx) / span if span > 0 else 0.0
            progress_map[i] = start_prog + (end_prog - start_prog) * ratio

    if speech_count > 0:
        progress_map[-1] = 1.0

    return progress_map


def apply_curve_to_blocks(blocks: list[dict], curve: ProsodyCurve) -> list[dict]:
    """在 block 列表上应用韵律弧线：注入 speed/vol，插入自动停顿。"""
    progress_map = _build_progress_map(blocks)

    speech_order = 0
    result = []

    for i, block in enumerate(blocks):
        if block["type"] == "phase_marker":
            continue  # 阶段标记不输出

        if block["type"] != "speech":
            result.append(block)
            continue

        progress = progress_map[speech_order] if speech_order < len(progress_map) else 1.0
        base_speed, base_vol, base_pause = curve.interpolate(progress)

        # 应用内联标记乘法系数
        multiplier = block.get("multiplier")
        if multiplier:
            base_speed *= multiplier.get("speed", 1.0)
            base_vol *= multiplier.get("volume", 1.0)

        new_block = dict(block)
        new_block["speed"] = base_speed
        new_block["vol"] = base_vol
        new_block["progress"] = progress

        # 自动句间停顿（在当前 speech block 之前插入，除非是第一个）
        if speech_order > 0:
            pause_dur = base_pause
            if block.get("paragraph_start"):
                pause_dur *= 1.5
            result.append({"type": "auto_pause", "sec": pause_dur, "progress": progress})

        result.append(new_block)
        speech_order += 1

    return result
