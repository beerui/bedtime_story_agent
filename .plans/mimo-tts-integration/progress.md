# MiMo-V2.5-TTS 集成 - 进度日志

> 按时间线记录。每条记录谁做了什么。

---

## 2026-05-01 Session 1 — 团队搭建

### 已完成
- [x] 需求咨询：确认集成 MiMo-V2.5-TTS 系列
- [x] 团队配置：5 个智能体（backend-dev, frontend-dev, researcher-technical, researcher-product, reviewer）
- [x] 创建 .plans/ 目录结构和规划文件

### 待办
- [x] 生成智能体并启动 Phase 0 调研
- [ ] 等待剩余智能体完成 Phase 0（researcher-technical, researcher-product, architect）

## 2026-05-01 Session 2 — Phase 0 进展

### 已完成
- backend-dev: 代码库调研完成，找到 MiMo 插入点 (engine.py L664)
- reviewer: baseline 分析完成，9 条发现 + 12 项审查清单
- architect: 启动代码库审计

### 已完成
- [x] researcher-technical: prosody-MiMo 映射调研完成（T0a）— 六段式分段方案
- [x] researcher-product: 市场/变现调研完成（T0b）— $80B 市场，推荐 YouTube+播客路径
- [x] frontend-dev: 站点结构分析完成 — 22 期节目，publish.py 构建，无主播概念

### 待办
- [x] architect: 代码库审计（Ta1）完成 + 重构方案（Ta2）待启动
- [ ] backend-dev: 开始 T1a（MiMo TTS API 集成）— 等待派单

## 2026-05-01 Session 3 — architect 审计完成

### 已完成
- [x] architect Ta1: 代码库审计完成
  - 审计范围: engine.py (1035行), config.py (409行), prosody.py (160行), batch.py (282行), tests/ (854行), publish.py (4805行)
  - 发现 5 个 CRITICAL/HIGH 级问题
  - MiMo 集成建议架构: BaseTTSEngine 抽象层 + MiMoTTSEngine + TTSManager
  - 预计 MiMo 集成工作量 ~13.5h
  - 报告: `architect/task-codebase-audit/findings.md`

### 待办
- [ ] team-lead: 审批 Ta1 审计结果
- [ ] architect: Ta2 重构方案 — 等待审批后启动

## 2026-05-01 Session 4 — 项目架构重构

### 已完成
- [x] **engine.py 拆分** (981行 → 5 个模块 + 1 个 facade)
  - `story_gen.py` (245行) — 3-pass 剧本生成 + 质量评估 + 章节标题
  - `audio_gen.py` (275行) — TTS 合成流水线 + 混音 + 响度归一化 + 底噪
  - `visual_gen.py` (248行) — 封面/场景图/AI 视频/视频合成
  - `bgm.py` (68行) — AI 选曲 + YouTube 下载
  - `metadata_gen.py` (104行) — 元数据生成 + 质量校验
  - `engine.py` (46行) — thin facade，向后兼容所有 import
- [x] **publish.py 拆分** (4805行 → 8 个模块 + 1 个入口)
  - `publish/core.py` (442行) — 常量/扫描/部署/工具函数
  - `publish/rss.py` (140行) — RSS 订阅源生成
  - `publish/pages.py` (1166行) — 共享 HTML 构建器 + 首页
  - `publish/pages_episode.py` (863行) — 单期页生成
  - `publish/pages_taxy.py` (796行) — 主题/分类/统计页
  - `publish/pages_legal.py` (653行) — 法律/关于/FAQ/站点地图
  - `publish/pages_common.py` (146行) — 共享常量/表单构建器
  - `publish/pwa.py` (200行) — PWA manifest + service worker
  - `publish.py` (320行) — CLI 入口
- [x] **CI 更新**: 新增 test_publish_helpers 到 run_ci.py
- [x] **测试验证**: 99 测试全部通过，黄金原则 0 失败

### 代码质量指标
| 指标 | 重构前 | 重构后 |
|------|--------|--------|
| 最大单文件 | publish.py 4805行 | pages.py 1166行 |
| engine.py | 981行 | 46行 (facade) |
| 黄金原则 GR-1 | 1 FAIL | 0 FAIL |
| 测试通过 | 66 | 99 |

## 2026-05-01 Session 5 — MiMo LLM 文案生成集成

### 已完成
- [x] **config.py**: 新增 `MI_BASE_URL`、`MI_TEXT_MODEL` 配置项
- [x] **story_gen.py**: MiMo LLM 优先 + Qwen fallback
  - 新增 `_mimo_text_client` 客户端
  - `_llm_call` → `_llm_raw` 统一 fallback 逻辑
  - `_generate_chapter_titles`、`_evaluate_story`、`generate_custom_theme` 全部走 fallback
- [x] **metadata_gen.py**: 同样 MiMo 优先 + Qwen fallback
  - 新增 `_llm_raw` helper
  - `generate_publish_metadata` 使用 fallback
- [x] **bgm.py**: `select_best_bgm` 走 MiMo fallback
- [x] **tests/test_mimo_llm.py**: 13 个测试覆盖 fallback 行为
  - story_gen: MiMo 成功跳过 Qwen / MiMo 失败降级 / 两者都失败返回 None / _llm_call 抛异常
  - metadata_gen: 同上（moviepy 不可用时自动 skip）
  - bgm: 选曲 fallback
  - config: MI_BASE_URL / MI_TEXT_MODEL 默认值
- [x] **scripts/run_ci.py**: 新增 test_mimo_llm 到 CI

### 代码质量指标
| 指标 | Session 4 | Session 5 |
|------|-----------|-----------|
| 测试通过 | 99 | 112 |
| CI 通过 | 2/2 | 2/2 |

### 修复
- [x] **MiMo endpoint**: 默认改为 `https://token-plan-cn.xiaomimimo.com/v1`（tokenPLAN 专用）
- [x] **mimo_tts.py**: 音频响应 `audio` 是 dict，修复 `getattr` → `dict.get`
- [x] **mimo_tts.py**: `MIMO_BASE_URL` 改为从 config 读取 `MI_BASE_URL`，消除硬编码

### 验证结果
- MiMo LLM 文本生成: 通过（`mimo-v2.5` 模型）
- MiMo TTS 语音合成: 通过（需设置 `TTS_ENGINE=mimo`）
- TTS fallback 链: MiMo → CosyVoice → edge-tts 正常工作

### 待办
- [ ] 更新 MI_API_KEY（当前 key 已失效）
- [ ] 验证 MiMo LLM 文本生成质量（需要有效 key）
- [ ] T1c: 多主播音色管理（每个主题绑定 Voice Design 描述）
- [ ] T1d: 风格标签自动生成（LLM 为每段脚本生成 MiMo 风格标签）
