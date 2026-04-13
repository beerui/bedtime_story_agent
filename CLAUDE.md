# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bedtime Story Agent — an automated pipeline that produces sleep/meditation videos end-to-end: AI-written script, TTS narration, scene images, AI-generated video clips, BGM selection, multi-platform cover art, and final video assembly.

## Running

```bash
# Full interactive pipeline (new or resumed project)
python main.py

# Module-by-module debug (story / TTS / image / video individually)
python debug.py

# Standalone TTS synthesis
python synthesize_once.py "要合成的文字"
python synthesize_once.py -o outputs/my.mp3 "文字"
```

## Testing

```bash
# Unit tests (mock-based, no API keys needed)
python -m unittest tests.test_cosyvoice_synthesize -v

# Live TTS integration test (requires COSYVOICE_API_KEY in .env)
RUN_COSYVOICE_LIVE=1 python -m unittest tests.test_cosyvoice_live -v
```

## Architecture

Three files form the core:

- **`config.py`** — loads `.env`, exposes `API_CONFIG` dict, theme definitions (`THEMES`), and `TTS_SCRIPT_DIRECTIVE` (the markup spec the LLM must follow when writing scripts).
- **`engine.py`** — all production modules: story generation (multi-agent chain), TTS (CosyVoice / edge-tts fallback), image generation (Pollinations), AI video (Aliyun Wan2.x with model fallback), BGM selection, cover art, and final video assembly.
- **`main.py`** — interactive CLI entry point. Dispatches four concurrent `asyncio` branches (visuals, BGM, story+audio, covers) then optionally renders the final MP4.

### Pipeline concurrency model

`main.py` fires four independent tasks via `asyncio.gather`:

1. **Visuals** — generate scene image, then send to AI video model
2. **BGM** — AI picks from local `assets/` or downloads via yt-dlp
3. **Story + Audio** — 3-pass LLM story generation, then segment-by-segment TTS with physical silence splicing
4. **Cover art** — 1920x1920 base image, auto-cropped to B站/抖音/小红书 ratios

### TTS markup system

The LLM writes scripts containing inline markup tags (`[停顿]`, `[停顿500ms]`, `[环境音：描述]`, `[慢速]`, `[轻声]`, `[极弱]`). `engine.generate_audio` tokenizes these into speech/break/prosody blocks, synthesizes each speech block independently with per-block speed/volume, applies fade-in/fade-out to eliminate hard cuts, then concatenates via moviepy. The markup spec is defined in `config.TTS_SCRIPT_DIRECTIVE`.

### CosyVoice model routing

`engine._cosyvoice_model_for_voice()` maps voice names to the correct CosyVoice model generation (v1/v2/v3-flash). Voice and model must be same generation or the API returns 418.

### AI video fallback chain

`engine.generate_ai_video` tries models in order (`wanx2.1-i2v-plus` → `wanx2.1-i2v-turbo` → `wan2.6-i2v-flash`). If all fail, the caller falls back to Ken Burns (static pan/zoom).

## Key Constraints

- **moviepy v1 only** — `main.py` blocks startup on moviepy >= 2.0. Uses `moviepy.editor` imports which don't exist in v2.
- Pillow/moviepy compatibility: `engine.py` patches `PIL.Image.ANTIALIAS = PIL.Image.LANCZOS` at module top.
- All API keys come from `.env` (see `.env.example`). `config.py` has a lightweight loader — no `python-dotenv` dependency.
- `SKIP_FINAL_VIDEO_RENDER=true` (default) skips the heavy FFmpeg render pass; set to `false` for full MP4 output.
- Test stubs (`tests/stub_engine_imports.py`) mock all heavy dependencies (moviepy, edge_tts, numpy, yt_dlp, dashscope, rich) so unit tests run without installing them.

## External Services

| Service | Purpose | Config key |
|---------|---------|------------|
| OpenAI-compatible proxy | Story text generation | `PROXY_API_KEY`, `PROXY_BASE_URL`, `TEXT_MODEL` |
| Aliyun DashScope CosyVoice | TTS narration | `COSYVOICE_API_KEY`, `TTS_VOICE` |
| Aliyun DashScope Wan2.x | Image-to-video | same `COSYVOICE_API_KEY` |
| Pollinations (free, no key) | Scene image + cover generation | — |
| edge-tts (free, no key) | TTS fallback when CosyVoice unconfigured | — |
