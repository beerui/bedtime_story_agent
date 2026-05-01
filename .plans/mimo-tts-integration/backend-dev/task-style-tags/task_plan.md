# 风格标签自动生成 - 任务计划

> 所属智能体: backend-dev
> 状态: pending (blocked by T0a, T1a)
> 创建: 2026-05-01

## 目标

在故事生成 pipeline 中，让 LLM 为每段脚本自动生成对应的 MiMo 风格标签或导演模式指令。

## 详细步骤

- [ ] 1. 分析现有 prosody.py 的阶段标记和内联标签系统
- [ ] 2. 设计 prosody curve → MiMo 风格标签的映射规则（依赖 T0a 调研结论）
- [ ] 3. 在故事生成 pipeline 中添加风格标签生成步骤
- [ ] 4. 实现 _build_mimo_style_tag() 函数
- [ ] 5. 确保风格标签与 prosody curve 参数一致（INV-10）
- [ ] 6. 编写测试
- [ ] 7. 请求 reviewer 审查

## 涉及文件

- `engine.py` — 添加风格标签生成逻辑
- `prosody.py` — 添加 prosody_to_mimo_style() 映射函数
- `config.py` — 风格标签配置

## 依赖

- 依赖 T0a (prosody-MiMo 映射调研结论)
- 依赖 T1a (mimo_tts.py 模块完成)
