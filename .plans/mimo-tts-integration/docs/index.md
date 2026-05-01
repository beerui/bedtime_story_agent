# MiMo-V2.5-TTS 集成 - 知识库索引

> 动态导航地图。team-lead 维护此文件。
> 智能体：需要在 docs/ 中查找信息时先 Read 此文件。

| 文档 | 关键 Sections | 最后更新 |
|------|-------------|---------|
| architecture.md | §系统概览 (L1-15): 整体流程 · §TTS Fallback 链 (L17-25): 三级降级 · §MiMo 集成架构 (L27-42): 模块划分 · §数据流 (L44-60): 脚本→音频 | 2026-05-01 |
| api-contracts.md | §MiMo API (L1-35): 外部接口 · §内部接口 (L37-55): mimo_tts.py | 2026-05-01 |
| invariants.md | §音频质量 (L1-8): 质量边界 · §降级规则 (L10-18): fallback 不变量 · §数据隔离 (L20-25): API Key 安全 | 2026-05-01 |

## 如何使用此索引

- 需要了解 TTS 架构？→ 读 architecture.md §系统概览
- 需要 MiMo API 字段？→ 读 api-contracts.md §MiMo API
- 需要检查变更是否违反边界？→ 读 invariants.md
