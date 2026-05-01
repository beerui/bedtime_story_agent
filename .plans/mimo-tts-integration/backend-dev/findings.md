# backend-dev - 发现索引

> 纯索引——每个条目应简短（Status + Report 链接 + Summary）。

---

## [P0] Phase 0: 代码库调研 (T1a 前置)

**Status**: DONE
**Report**: [phase0-codebase-investigation/findings.md](phase0-codebase-investigation/findings.md)
**Summary**: 全面梳理了 engine.py / config.py / prosody.py 的 TTS 实现现状。核心发现：(1) TTS fallback 是两级 CosyVoice→edge-tts，插入 MiMo 需要在 `generate_audio` 函数第 664 行的 if 分支前插入；(2) prosody curve 参数 (speed/volume/pause) 需要映射为 MiMo 的 style text；(3) config.py 已有 `THEME_VOICE_MAP` 可扩展为 MiMo Voice Design 映射。

