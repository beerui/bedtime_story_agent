# Pipeline Fix & Prosody Curve Engine Design

## Overview

Two-phase project:
- **Phase 1**: Fix bugs and missing deps so the pipeline runs end-to-end
- **Phase 2**: Build a Prosody Curve Engine for hypnotic rhythm control, plus improve LLM prompts for rhythm-aware scriptwriting

---

## Phase 1: Bug Fixes — Make the Pipeline Run

### 1.1 Create `requirements.txt`

Pin all dependencies. Critical: `moviepy<2.0` (v2 removes `moviepy.editor`).

```
moviepy>=1.0.3,<2.0
dashscope>=1.14.0
edge-tts>=6.1.0
yt-dlp>=2024.0.0
Pillow>=9.0.0
rich>=13.0.0
openai>=1.0.0
numpy>=1.20.0
requests>=2.28.0
```

### 1.2 Fix `_synthesize_cosyvoice` model routing

**Bug**: `engine.py:323` hardcodes `model='cosyvoice-v3-flash'`, ignoring `_cosyvoice_model_for_voice()`.

**Fix**: Replace hardcoded model with:
```python
model=_cosyvoice_model_for_voice(API_CONFIG.get('tts_voice', 'longxiaochun'))
```

### 1.3 Fix default speech rate

**Bug**: `_synthesize_cosyvoice` defaults to `speed=1.0`, but sleep content should default slower.

**Fix**: Change default to `speed=0.8`. This matches test expectations and the app's purpose.

### 1.4 Completion criteria

- All 5 unit tests in `test_cosyvoice_synthesize.py` pass
- `python3 main.py` completes a full run with `SKIP_FINAL_VIDEO_RENDER=true` (requires API keys in `.env`)

---

## Phase 2: Prosody Curve Engine

### 2.1 Core concept: Prosody Curve

A function mapping script progress (0.0 → 1.0) to `{speed, volume, pause_gap}`. Defined as piecewise-linear control points in `config.py`:

```python
PROSODY_CURVES = {
    "hypnotic": {
        "speed":  [(0.0, 1.0), (0.3, 0.9), (0.7, 0.75), (1.0, 0.55)],
        "volume": [(0.0, 1.0), (0.5, 0.85), (0.8, 0.6),  (1.0, 0.3)],
        "pause":  [(0.0, 0.3), (0.5, 0.6),  (0.8, 1.2),  (1.0, 2.0)],
    },
}
CURRENT_PROSODY_CURVE = "hypnotic"
```

Meaning: speech starts at normal speed/volume with 0.3s inter-sentence pauses. By 70% through the script, speed drops to 0.75x, volume to 0.6x, pauses grow to 1.2s. At the end: speed 0.55x, volume 0.3x, pauses 2.0s.

### 2.2 New file: `prosody.py` (~80 lines)

```
class ProsodyCurve:
    __init__(curve_config: dict)
    interpolate(progress: float) -> tuple[float, float, float]
        # returns (speed, volume, pause_seconds)
        # Linear interpolation between control points

def apply_curve_to_blocks(blocks: list[dict], curve: ProsodyCurve) -> list[dict]:
    # 1. Count total speech blocks to determine each block's progress position
    # 2. For each speech block:
    #    - Get (base_speed, base_vol, base_pause) from curve.interpolate(progress)
    #    - If block has inline tags ([慢速]/[轻声]/[极弱]), multiply on top of base
    #    - Set block's final speed/vol
    # 3. Between consecutive speech blocks, insert auto-pause blocks
    #    with duration = base_pause (or base_pause * 1.5 at paragraph boundaries)
    # 4. Return modified block list
```

### 2.3 Inline tag semantics change: absolute → multiplicative

Current behavior: `[慢速]` sets speed=0.8, `[轻声]` sets vol=0.4, `[极弱]` sets speed=0.6/vol=0.2. After the sentence, resets to 1.0/1.0.

New behavior: Tags are **multipliers** applied on top of the curve's base value:

| Tag | Speed multiplier | Volume multiplier |
|-----|-----------------|-------------------|
| `[慢速]` | ×0.8 | ×1.0 |
| `[轻声]` | ×1.0 | ×0.5 |
| `[极弱]` | ×0.7 | ×0.3 |

Example at script progress 0.8 (curve base: speed=0.75, vol=0.6):
- No tag: speed=0.75, vol=0.6
- `[极弱]`: speed=0.75×0.7=0.525, vol=0.6×0.3=0.18

This produces natural gradual intensification — the same tag has stronger effect later in the script.

### 2.4 Changes to `engine.generate_audio`

Current flow: `tokens → blocks → synthesize → concatenate`

New flow:
1. **Tokenize** (unchanged) — parse text/break/prosody tokens
2. **Build blocks** (minor change) — prosody tokens store multipliers instead of absolute values
3. **Apply curve** (new step) — `apply_curve_to_blocks(blocks, curve)` injects base speed/vol and auto-pauses
4. **Synthesize** (unchanged) — per-block TTS calls with computed speed
5. **Post-process concatenation** (enhanced) — see 2.5

### 2.5 Enhanced post-processing: breathing feel

Current: fixed fade-in 0.1s, fade-out 0.4s for all clips.

New: fade durations scale with curve progress:
- `fade_in = 0.05 + 0.15 * progress` (0.05s → 0.20s)
- `fade_out = 0.2 + 0.6 * progress` (0.2s → 0.8s)

Effect: early sentences have crisp starts and moderate tails. Late sentences have soft onsets and long, melting tails — the "sinking into sleep" feel.

### 2.6 Paragraph boundary detection

To apply 1.5x pause at paragraph breaks, detect boundaries in the tokenizer:
- Two or more consecutive newlines → paragraph boundary
- `[环境音：...]` tag → always treated as paragraph boundary

Mark paragraph-final speech blocks with a `paragraph_end=True` flag. `apply_curve_to_blocks` uses this to scale the auto-pause.

---

## Phase 2B: LLM Prompt Improvements

### 2B.1 Rhythm structure template

Add to `TTS_SCRIPT_DIRECTIVE`:

```
【全篇节奏结构 — 必须遵守】
- 引入段（前 30%）：正常句长 15-25 字，自然口语节奏，每 2-3 句用一个 [停顿]。
- 深入段（30%-70%）：句长渐短 10-18 字，[停顿] 频率增加，开始出现 [环境音：] 留白。
- 尾声段（后 30%）：极短句 5-12 字，大量 [停顿1s] 和 [停顿2s]，可用 [慢速]、[轻声]、[极弱]。
  最后 3-5 句必须极短，每句之间用 [停顿2s] 以上分隔。
```

### 2B.2 Phase markers

Require the LLM to insert `[阶段：引入]`、`[阶段：深入]`、`[阶段：尾声]` markers. These are stripped before TTS, but used by `apply_curve_to_blocks` to snap curve progress to phase boundaries instead of pure linear interpolation.

Tokenizer change: recognize `[阶段：XXX]` as a new token type `phase_marker`. `apply_curve_to_blocks` uses these as anchors to remap progress:

| Phase marker | Maps to curve progress |
|---|---|
| `[阶段：引入]` | 0.0 |
| `[阶段：深入]` | 0.3 |
| `[阶段：尾声]` | 0.7 |

Between anchors, progress is linearly interpolated across the actual speech blocks in that segment. This means if the LLM writes a longer introduction (50% of blocks) but marks `[阶段：深入]` there, the curve spends progress 0.0→0.3 spread over those 50% of blocks — effectively slowing the curve progression during the intro and compressing it during the ending. Without any phase markers, progress falls back to pure linear (block_index / total_blocks).

### 2B.3 Anti-AI-tone specifics

Add to the editor-pass prompt (the 3rd LLM call in `generate_story`):

```
【禁止清单】：
- 排比不超过两组
- 不以反问句结尾
- 禁止「让我们」「我们一起」等集体感措辞
- 禁止「你有没有想过」「其实」等说教开头
- 每段至少一个具体感官细节（触觉/嗅觉/温度/声音质感）
```

---

## File change summary

| File | Change type | Description |
|------|-------------|-------------|
| `requirements.txt` | New | Dependency pinning |
| `engine.py` | Fix | `_synthesize_cosyvoice` model routing + default speed |
| `prosody.py` | New | `ProsodyCurve` class + `apply_curve_to_blocks` |
| `config.py` | Add | `PROSODY_CURVES`, `CURRENT_PROSODY_CURVE`, enhanced `TTS_SCRIPT_DIRECTIVE` |
| `engine.py` | Modify | `generate_audio` integrates prosody curve; `generate_story` enhanced prompts |
| `tests/test_prosody.py` | New | Unit tests for ProsodyCurve interpolation and block transformation |
| `tests/test_cosyvoice_synthesize.py` | No change | Existing tests should still pass after Phase 1 fixes |

## Minor cleanup (during implementation)

- Consolidate duplicate pause parsing: `engine.generate_audio` has a local `parse_pause` function that duplicates module-level `_silence_seconds_for_markup`. Replace with a single shared implementation in `prosody.py`.

## Out of scope

- Switching TTS backend (future work, architecture supports it)
- Final video render pipeline fixes (separate concern)
- New theme creation
- BGM selection improvements
