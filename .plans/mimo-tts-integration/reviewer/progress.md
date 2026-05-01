# reviewer - 工作日志

> 用于上下文恢复。压缩/重启后先读此文件。

---

## 2026-05-01 — Phase 0: 代码库熟悉

### 已完成

- 阅读 engine.py (1036行): 理解完整 TTS 流水线
  - `_synthesize_cosyvoice()` — CosyVoice 底层合成
  - `generate_audio()` — 主音频流水线 (词法解析 → prosody 应用 → 合成拼接)
  - fallback 逻辑: CosyVoice 失败 → edge-tts，AllocationQuota 触发全局禁用
- 阅读 config.py (410行): API 配置、13 个主题定义、prosody curve、edge-tts 音色映射
- 阅读 prosody.py (161行): ProsodyCurve 插值、phase markers、TAG_MULTIPLIERS
- 阅读 batch.py (283行): 批量生产 CLI、并发控制、去重
- 阅读全部测试:
  - test_cosyvoice_synthesize.py (5 tests) — mock CosyVoice 底层
  - test_prosody.py (16 tests) — prosody 引擎完整覆盖
  - test_cosyvoice_live.py (1 test) — 集成测试，需 API key
  - test_publish_helpers.py — 发布元数据测试
- 阅读团队文档: architecture.md, api-contracts.md, invariants.md

### 关键发现

- engine.py 单文件 1036 行，MiMo 集成将使其进一步膨胀 → 建议 backend-dev 优先抽取 mimo_tts.py
- `generate_audio()` 是核心但无单元测试 → MiMo 集成后需新增测试
- `_synthesize_cosyvoice` 无超时 → MiMo 合成同样需要超时机制 (INV-2)
- fallback 链现有逻辑清晰，MiMo 需在此基础上扩展

### 当前状态

- T2a (代码审查) 阻塞于 Phase 1 全部任务
- 已生成 baseline findings (9 条) + 审查清单 (12 项)
- 等待 backend-dev 完成 T1a-T1d 后启动正式审查
