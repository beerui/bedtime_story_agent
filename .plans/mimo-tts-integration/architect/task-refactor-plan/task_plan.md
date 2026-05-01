# 重构方案 - 任务计划

> 所属智能体: architect
> 状态: pending (blocked by Ta1)
> 创建: 2026-05-01

## 目标

基于代码库审计结果，制定重构方案，与 MiMo TTS 集成协调进行。

## 详细步骤

- [ ] 1. 读取审计报告（task-codebase-audit/findings.md）
- [ ] 2. 确定重构优先级（哪些必须在 MiMo 集成前完成）
- [ ] 3. 设计模块拆分方案（如 engine.py → tts.py / story.py / audio.py）
- [ ] 4. 设计 TTS 抽象层（统一 CosyVoice/MiMo/edge-tts 接口）
- [ ] 5. 评估重构风险和工作量
- [ ] 6. 将重构方案写入 findings.md
- [ ] 7. 通知 team-lead 审批

## 涉及文件

- 由审计结果决定

## 依赖

- 依赖 Ta1（代码库审计完成）
