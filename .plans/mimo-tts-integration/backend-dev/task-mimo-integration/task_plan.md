# MiMo TTS API 集成 - 任务计划

> 所属智能体: backend-dev
> 状态: pending
> 创建: 2026-05-01

## 目标

创建独立的 mimo_tts.py 模块，实现 MiMo-V2.5-TTS API 调用，支持预置音色和 Voice Design。

## 详细步骤

- [ ] 1. 创建 mimo_tts.py，实现 OpenAI-compatible SDK 调用
- [ ] 2. 实现 synthesize_mimo_preset() — 预置音色模式
- [ ] 3. 实现 synthesize_mimo_voicedesign() — Voice Design 模式
- [ ] 4. 实现 synthesize_mimo() — 统一入口
- [ ] 5. 在 config.py 添加 MiMo 配置（API Key、音色映射、主播配置）
- [ ] 6. 编写单元测试（mock API response）
- [ ] 7. 请求 reviewer 审查

## 涉及文件

- `mimo_tts.py` — 新建，MiMo TTS 独立模块
- `config.py` — 添加 MiMo 配置
- `engine.py` — 参考现有 _synthesize_cosyvoice() 实现
- `tests/test_mimo_tts.py` — 新建，单元测试

## 依赖

- 依赖 researcher-technical 的 T0a 调研结论（prosody→MiMo 映射方案）
- MiMo API 文档见 .plans/mimo-tts-integration/docs/api-contracts.md
