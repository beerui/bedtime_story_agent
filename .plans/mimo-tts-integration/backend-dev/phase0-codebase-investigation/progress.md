# Phase 0: 代码库调研 — 进度日志

## 2026-05-01

- 读取 engine.py (1036行)：梳理了 `_synthesize_cosyvoice` (L535-555) 和 `generate_audio` (L557-721) 的完整 TTS 流程
- 读取 config.py (410行)：确认 API 配置、THEME_VOICE_MAP、PROSODY_CURVES 结构
- 读取 prosody.py (161行)：理解 ProsodyCurve 分段线性插值、PHASE_ANCHORS、TAG_MULTIPLIERS
- 读取 api-contracts.md：确认 MiMo API 字段定义和内部接口设计
- 读取 architecture.md：确认 TTS fallback 链设计 (MiMo → CosyVoice → edge-tts)
- 产出: phase0-codebase-investigation/findings.md，包含 5 大板块详细发现

**下一步**: 等待 researcher-technical 的 T0a 调研结论（MiMo API 实测结果），然后开始 T1a 编码。
