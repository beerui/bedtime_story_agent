# MiMo-V2.5-TTS 集成 - 发现与技术记录

> 由团队智能体自动更新。每条标注来源。

---

标签说明:
- [RESEARCH] 调研发现
- [BUG] 缺陷记录
- [CODE-REVIEW] 代码审查结果
- [REVIEW-FIX] 审查问题修复
- [ARCHITECTURE] 架构分析
- [INTEGRATION] 集成问题

---

## [MARKET] researcher-product: 睡前音频市场分析 (2026-05-01)

**报告位置**: `researcher-product/research-market/findings.md`

**核心结论**:
1. 全球助眠+冥想市场合计超 $80B，CAGR 8-20%，市场空间充足
2. 头部竞品（Calm $200M+/年，Headspace $150-200M/年）验证了付费意愿
3. AI 批量生产线成本低 1000x、产量高 100x，具备结构性优势
4. 推荐变现路径：YouTube+播客矩阵（快速验证） → 国内音频平台 → 自有产品+B2B
5. 本项目 Prosody Curve + 3-pass LLM 为核心技术壁垒

---

## [ARCHITECTURE] architect: 代码库审计完成 (2026-05-01)

**报告位置**: `architect/task-codebase-audit/findings.md`

**核心发现**:
1. CRITICAL: engine.py 1035行/20函数，职责严重过重（TTS/视频/图片/混音/元数据全在一起）
2. CRITICAL: TTS 模块无抽象层，CosyVoice/edge-tts 直接硬编码在 generate_audio() 的 if/else 中，MiMo 无法干净集成
3. HIGH: 核心流水线（generate_audio / generate_story / mix_final_audio）零测试覆盖
4. HIGH: 裸 except 滥用（L247, L1030），吞掉所有异常
5. MEDIUM: BGM 路径查找逻辑重复两处

**MiMo 集成建议**:
- 必须先提取 TTS 抽象层 (tts_engine.py + mimo_tts.py)，否则集成会进一步恶化 engine.py
- 建议架构: BaseTTSEngine -> MiMoTTSEngine / CosyVoiceTTSEngine / EdgeTTSEngine -> TTSManager
- 预计 MiMo 集成工作量 ~13.5h

**重构建议（优先级排序）**:
- P0: 提取 TTS 抽象层 (MiMo 集成前提)
- P1: 修改 engine.py 接入 TTSManager + 添加测试
- P2: 拆分 engine.py / 提取主题配置到独立文件
- P3: 拆分 publish.py (4805行) / 改进异常处理
