# backend-dev - 任务计划

> 角色: 后端开发
> 状态: pending
> 分配的任务: T1a (MiMo 集成), T1b (fallback 链), T1c (多主播), T1d (风格标签)

## 任务

- [ ] T1a: MiMo TTS API 集成 — 创建 mimo_tts.py 独立模块
- [ ] T1b: TTS fallback 链重构 — MiMo → CosyVoice → edge-tts
- [ ] T1c: 多主播音色管理 — 主题→Voice Design 映射配置
- [ ] T1d: 风格标签自动生成 — LLM 为每段脚本生成 MiMo 风格标签

## 备注

- 依赖 researcher-technical 的 T0a 调研结论（prosody→MiMo 映射方案）
- 关键文件：engine.py, config.py, prosody.py
- MiMo API 使用 openai SDK，base_url=https://api.xiaomimimo.com/v1
- API Key 在 .env 中为 MI_API_KEY
