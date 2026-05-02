# MiMo-V2.5-TTS 集成 - 主计划

> 状态: IN_PROGRESS
> 创建: 2026-05-01
> 更新: 2026-05-02
> 团队: mimo-tts-integration (backend-dev, frontend-dev, researcher-technical, researcher-product, reviewer, architect)
> 决策记录: .plans/mimo-tts-integration/decisions.md

---

## 1. 项目概述

将小米 MiMo-V2.5-TTS 系列集成到 bedtime_story_agent 的 TTS 流水线中。支持预置音色、Voice Design 多主播、风格标签/导演模式，提升音频质量和内容差异化。同时进行产品/市场调研确保商业可行性。

详细产品定义 → [docs/architecture.md](docs/architecture.md)

---

## 2. 文档索引

| 文档 | 位置 | 内容 |
|------|------|------|
| 架构 | docs/architecture.md | TTS fallback 链、MiMo 集成架构、数据流 |
| API 契约 | docs/api-contracts.md | MiMo API 接口定义、内部 TTS 抽象层接口 |
| 不变量 | docs/invariants.md | 音频质量边界、降级规则 |
| 导航地图 | docs/index.md | 各文档 section 级导航 |

---

## 3. 阶段概览

### Phase 0: 调研（并行）— ✅ 完成

| # | 任务 | 负责人 | 状态 | 计划文件 |
|---|------|--------|------|----------|
| T0a | prosody-MiMo 映射调研 | researcher-technical | **COMPLETE** | researcher-technical/research-prosody-mimo/task_plan.md |
| T0b | 市场/变现调研 | researcher-product | **COMPLETE** | researcher-product/research-market/task_plan.md |
| Ta1 | 代码库审计 | architect | **COMPLETE** | architect/task-codebase-audit/task_plan.md |
| Ta2 | 重构方案 | architect | **COMPLETE** | architect/task-refactor-plan/task_plan.md |

### Phase 1: 核心开发（依赖 T0a）— ⏳ 进行中

| # | 任务 | 负责人 | 状态 | 计划文件 |
|---|------|--------|------|----------|
| T1a | MiMo TTS API 集成 | backend-dev | **IN_PROGRESS** | backend-dev/task-mimo-integration/task_plan.md |
| T1b | TTS fallback 链重构 | backend-dev | pending (blocked by T1a) | backend-dev/task-fallback-chain/task_plan.md |
| T1c | 多主播音色管理 | backend-dev | pending (blocked by T1a) | backend-dev/task-mimo-integration/task_plan.md |
| T1d | 风格标签自动生成 | backend-dev | pending (blocked by T0a, T1a) | backend-dev/task-style-tags/task_plan.md |
| T1e | episode 页面适配 | frontend-dev | pending (blocked by T1c) | frontend-dev/task-episode-mimo/task_plan.md |

### Phase 2: 审查 + 质量保证

| # | 任务 | 负责人 | 状态 | 计划文件 |
|---|------|--------|------|----------|
| T2a | 代码审查 | reviewer | pending (blocked by T1a-T1e) | reviewer/ |
| T2b | 音频质量验证 | backend-dev | pending (blocked by T2a) | backend-dev/ |

---

## 4. 当前阶段

Phase 1 — 核心开发阶段。

### 已完成（Session 4-5）
- ✅ engine.py 拆分（981行 → 5 个模块 + 1 个 facade）
- ✅ publish.py 拆分（4805行 → 8 个模块 + 1 个入口）
- ✅ MiMo LLM 文本生成集成（story_gen/metadata_gen/bgm 已接入 fallback）

### 当前任务（T1a）
- ⏳ MiMo TTS API 集成
- 目标：提取 TTS 抽象层 + 创建 mimo_tts.py + 接入 TTSManager
- 预计工作量：~13.5h
- 负责人：backend-dev

### 下一步
- T1b: TTS fallback 链重构（MiMo → CosyVoice → edge-tts）
- T1c: 多主播音色管理（每个主题绑定 Voice Design 描述）
- T1d: 风格标签自动生成（LLM 为每段脚本生成 MiMo 风格标签）
