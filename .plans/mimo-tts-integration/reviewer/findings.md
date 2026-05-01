# reviewer - 发现索引

> 纯索引——每个条目应简短（Status + Report 链接 + Summary）。

---

## Baseline Analysis (Phase 0)

| # | 级别 | 维度 | 文件 | 发现 | 状态 |
|---|------|------|------|------|------|
| B-01 | HIGH | 代码质量 | engine.py | engine.py 已超 1000 行，混合了 TTS/视频/图片/混音/元数据等全部模块，违反单一职责 | OPEN |
| B-02 | MEDIUM | 代码质量 | engine.py:247 | `select_best_bgm` 裸 except: 吞掉所有异常，含 API 错误 | OPEN |
| B-03 | MEDIUM | 代码质量 | engine.py:1030 | `assemble_pro_video` 中 TextClip 失败时裸 except: break，静默跳过字幕 | OPEN |
| B-04 | HIGH | 容错降级 | engine.py:535-556 | `_synthesize_cosyvoice` 无超时机制，INV-2 要求 30s 超时触发 fallback | OPEN |
| B-05 | MEDIUM | 代码质量 | engine.py:638 | `generate_audio` 循环中局部 `cosyvoice_disabled` 标志未持久化，多 episode 并发时可能重复尝试已耗尽的额度 | OPEN |
| B-06 | LOW | 代码质量 | engine.py:370 | `_generate_chapter_titles` 内 import json/re，应在文件顶部统一导入 | OPEN |
| B-07 | MEDIUM | 测试覆盖 | tests/ | `generate_audio` (核心音频流水线) 无单元测试，仅 CosyVoice 底层有 mock 测试 | OPEN |
| B-08 | LOW | 安全 | config.py:46 | API key 从 .env 加载且使用 `os.getenv(..., "")`，无硬编码，符合 INV-7 | OK |
| B-09 | MEDIUM | 性能 | engine.py:953 | `generate_multi_images` 轮询 Pollinations 4 次共超时 240s，无并发 | OPEN |

## MiMo Integration Review Checklist (Phase 2 用)

审查 Phase 1 变更时需逐项检查：

- [ ] INV-1: MiMo 输出有效音频 (wav/mp3, >=16kHz)
- [ ] INV-2: 30s 超时触发 fallback
- [ ] INV-3: MiMo 失败无感降级到 CosyVoice
- [ ] INV-4: Fallback 链顺序 MiMo -> CosyVoice -> edge-tts
- [ ] INV-6: MiMo 额度耗尽全局禁用
- [ ] INV-7: MI_API_KEY 从 .env 读取，无硬编码
- [ ] INV-8: 临时音频文件清理
- [ ] INV-9: MiMo API 使用 OpenAI-compatible SDK
- [ ] INV-10: 风格标签与 prosody curve 一致
- [ ] mimo_tts.py 是否可独立测试 (mock-friendly)
- [ ] 新增测试覆盖 MiMo 合成 + fallback 链
- [ ] config.py 新增配置项有默认值
- [ ] 无 CRITICAL/HIGH 遗留
