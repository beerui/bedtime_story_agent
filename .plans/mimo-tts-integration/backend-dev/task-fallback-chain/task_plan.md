# TTS Fallback 链重构 - 任务计划

> 所属智能体: backend-dev
> 状态: pending (blocked by T1a)
> 创建: 2026-05-01

## 目标

重构 engine.py 中的 TTS fallback 逻辑，加入 MiMo 作为首选引擎。

## 详细步骤

- [ ] 1. 在 engine.py 添加 _synthesize_mimo() 包装函数
- [ ] 2. 更新 fallback 逻辑：MiMo → CosyVoice → edge-tts
- [ ] 3. 实现 MiMo 失败时的无感降级
- [ ] 4. 更新 cosyvoice_disabled 逻辑，添加 mimo_disabled 全局标志
- [ ] 5. 更新日志输出，标注当前使用的 TTS 引擎
- [ ] 6. 运行现有测试确保不破坏
- [ ] 7. 请求 reviewer 审查

## 涉及文件

- `engine.py` — 修改 TTS fallback 逻辑（约 L637-676）
- `config.py` — 添加 MiMo 相关配置

## 依赖

- 依赖 T1a (mimo_tts.py 模块完成)
