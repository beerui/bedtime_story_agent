# MiMo-V2.5-TTS 集成 - 架构

> 系统架构和关键设计决策。
> 维护者：team-lead, backend-dev

## 系统概览

bedtime_story_agent 是一个睡前故事/冥想音频自动化生产线。核心流程：
1. LLM 生成故事脚本（含 prosody markup）
2. TTS 引擎将脚本转为语音
3. Prosody Curve Engine 控制语速/音量/停顿
4. BGM 混音 + 响度归一化
5. 多平台发布元数据生成

## TTS Fallback 链（重构后）

```
MiMo-V2.5-TTS (首选)
  ├── mimo-v2.5-tts (预置音色)
  ├── mimo-v2.5-tts-voicedesign (Voice Design)
  └── 失败? → CosyVoice (DashScope)
                └── 失败? → edge-tts (免费兜底)
```

## MiMo 集成架构

```
config.py
  ├── MI_API_KEY (from .env)
  ├── MIMO_VOICES (预置音色映射)
  └── MIMO_HOST_CONFIGS (主播 Voice Design 描述)

mimo_tts.py (新增独立模块)
  ├── synthesize_mimo_preset() — 预置音色
  ├── synthesize_mimo_voicedesign() — Voice Design
  └── synthesize_mimo() — 统一入口，自动选模型

engine.py (修改)
  ├── _synthesize_mimo() — 调用 mimo_tts.py
  ├── _build_mimo_style_tag() — 生成风格标签
  └── fallback 逻辑更新

prosody.py (修改)
  └── prosody_to_mimo_style() — prosody curve → MiMo 风格标签映射
```

## 数据流

```
故事脚本 (story_draft.txt)
  │
  ├─ [阶段标记] → prosody curve progress → MiMo 风格标签
  ├─ [内联标签] → multiplicative adjustment → MiMo 音频标签
  │
  ▼
mimo_tts.synthesize_mimo(text, voice, style)
  │
  ├─ 成功 → wav/pcm16 音频
  └─ 失败 → cosyvoice fallback → edge-tts fallback
  │
  ▼
音频后处理 (响度归一化 + BGM 混音)
```

## 技术栈

- Python 3.x
- openai SDK (MiMo API, OpenAI-compatible)
- dashscope SDK (CosyVoice)
- edge-tts (免费兜底)
- moviepy v1 (音频处理)
- GitHub Pages (静态站点)
