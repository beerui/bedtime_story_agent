# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bedtime Story Agent — an automated pipeline that batch-produces sleep/meditation audio content: AI-written scripts with prosody control, TTS narration with global rhythm curves, BGM mixing, and multi-platform publish metadata. Optionally generates scene images, AI video clips, and cover art.

## Running

```bash
# Batch production (recommended) — 3 random themes, audio-only
python3 batch.py --count 3 --audio-only

# Batch with specific themes
python3 batch.py --themes 午夜慢车 雨夜山中小屋 --audio-only

# Full sweep of all 13 themes
python3 batch.py --all --audio-only --words 600

# Interactive mode (legacy, includes visual pipeline)
python3 main.py

# Module-by-module debug
python3 debug.py

# Standalone TTS synthesis
python3 synthesize_once.py "要合成的文字"
```

## Testing

```bash
# All unit tests (28 tests, mock-based, no API keys needed)
python3 -m unittest tests.test_cosyvoice_synthesize tests.test_prosody -v

# Live TTS integration test (requires COSYVOICE_API_KEY in .env)
RUN_COSYVOICE_LIVE=1 python3 -m unittest tests.test_cosyvoice_live -v
```

## Architecture

### Core files

- **`config.py`** — loads `.env`, exposes `API_CONFIG`, theme definitions (`THEMES`), prosody curve configs (`PROSODY_CURVES`), edge-tts voice mappings, and `TTS_SCRIPT_DIRECTIVE`.
- **`engine.py`** — all production modules: story generation (3-pass LLM chain with quality evaluation), TTS (CosyVoice with auto-fallback to edge-tts), prosody-aware audio assembly, BGM mixing, image/video generation, cover art, SRT subtitle export, and publish metadata generation.
- **`prosody.py`** — Prosody Curve Engine: maps script progress (0→1) to speed/volume/pause curves. Supports phase markers (`[阶段：引入/深入/尾声]`) for non-linear progress mapping, and multiplicative inline tags.
- **`batch.py`** — batch production CLI. Integrates content dedup, quality evaluation, and metadata generation.
- **`dedup.py`** — TF-IDF cosine similarity dedup against all existing outputs.
- **`main.py`** — interactive CLI (legacy, full visual pipeline).

### Prosody Curve system

The core differentiator. A piecewise-linear curve maps script progress to `{speed, volume, pause_gap}`:
- Start: speed=1.0, vol=1.0, pause=0.3s (normal rhythm)
- End: speed=0.55, vol=0.3, pause=2.0s (deep sleep induction)

Inline tags (`[慢速]`, `[轻声]`, `[极弱]`) are **multiplicative** on the curve base — the same tag produces stronger effect later in the script.

Phase markers (`[阶段：引入]`, `[阶段：深入]`, `[阶段：尾声]`) snap curve progress to fixed anchors (0.0, 0.3, 0.7), allowing non-uniform progress distribution.

### TTS fallback chain

1. CosyVoice (model auto-routed by voice name via `_cosyvoice_model_for_voice`)
2. On quota exhaustion (`AllocationQuota`): globally disables CosyVoice for the session
3. edge-tts with theme-matched voice (`THEME_VOICE_MAP`) and prosody curve rate mapping

### Story generation pipeline

Three LLM passes + quality gate:
1. Outline (心理学大纲, with phase markers)
2. Draft expansion (口播稿, preserving all markup)
3. Editor pass (anti-AI-tone checklist, sensory detail enforcement)
4. Quality evaluation (4-dimension scoring, auto-rewrite if <70/100)

### Batch production output per episode

```
outputs/Batch_YYYYMMDD_HHMMSS_主题名/
├── story_draft.txt     # 剧本文稿
├── voice.mp3           # 纯配音
├── final_audio.mp3     # 成品（配音 + BGM 混音 + 响度归一化）
├── subtitles.srt       # SRT 字幕
├── metadata.json       # 发布元数据（标题/简介/标签，适配喜马拉雅/B站/小宇宙）
├── scene_1.png         # 场景图（非 --audio-only）
└── Cover_*.png         # 多平台封面（非 --audio-only）
```

## Key Constraints

- **moviepy v1 only** — v2 removes `moviepy.editor`. Pinned in `requirements.txt`.
- **Single DashScope API key** — `DASHSCOPE_API_KEY` in `.env` covers text (Qwen), TTS (CosyVoice), and video (Wan2.x). Falls back to edge-tts when TTS quota exhausted.
- DashScope is domestic; `config.py` auto-clears proxy env vars and sets SSL cert from certifi.
- Test stubs (`tests/stub_engine_imports.py`) mock heavy deps so unit tests run without moviepy/dashscope.

## External Services

| Service | Purpose | Config key |
|---------|---------|------------|
| Aliyun DashScope Qwen | Story text generation | `DASHSCOPE_API_KEY` |
| Aliyun DashScope CosyVoice | TTS narration | same key |
| Aliyun DashScope Wan2.x | Image-to-video | same key |
| Pollinations (free) | Scene image + cover generation | — |
| edge-tts (free) | TTS fallback, multiple Chinese voices | — |
