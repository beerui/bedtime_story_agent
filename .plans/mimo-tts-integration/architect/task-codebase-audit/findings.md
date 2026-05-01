# Ta1: 代码库审计报告

> 审计时间: 2026-05-01
> 审计范围: bedtime_story_agent 全项目
> 目标: 识别代码质量问题、技术债务、MiMo 集成切入点

---

## 1. 项目结构概览

### 1.1 文件统计

| 类别 | 文件数 | 总行数 | 说明 |
|------|--------|--------|------|
| 核心业务 | 6 | ~7,500 | engine.py, config.py, batch.py, prosody.py, main.py, dedup.py |
| 辅助工具 | 8 | ~2,000 | audio_fx.py, audio_tags.py, binaural.py, covers.py, doctor.py, launch.py, validate.py, preview.py |
| 测试 | 6 | ~854 | tests/ 目录 |
| 发布相关 | 2 | ~4,900 | publish.py (4805行), deploy.sh |
| 文档 | 3 | ~200 | CLAUDE.md, README.md, evolve.md |
| **合计** | ~25 | **~15,500** | |

### 1.2 关键发现

**CRITICAL: publish.py 文件过大 (4805行)**
- 路径: `/Users/motou/Desktop/bedtime_story_agent/publish.py`
- 问题: 单文件 4805 行，严重违反单一职责原则
- 影响: 难以维护、难以测试、代码审查困难

**HIGH: engine.py 职责过重 (1035行)**
- 路径: `/Users/motou/Desktop/bedtime_story_agent/engine.py`
- 问题: 混合了 15+ 个不同职责的函数
- 函数清单 (共 20 个顶层函数):
  - 封面生成: `generate_and_crop_cover()` (L50)
  - 视频特效: `apply_ken_burns()` (L110)
  - AI 视频生成: `generate_ai_video()` (L122)
  - 主题生成: `generate_custom_theme()` (L197)
  - BGM 管理: `download_bgm_from_youtube()` (L223), `select_best_bgm()` (L231)
  - 故事生成: `generate_story()` (L252), `_generate_chapter_titles()` (L364), `_evaluate_story()` (L413)
  - 噪音生成: `generate_soothing_noise()` (L465)
  - TTS 合成: `_cosyvoice_model_for_voice()` (L518), `_synthesize_cosyvoice()` (L535), `generate_audio()` (L557)
  - 字幕导出: `_export_srt()` (L724)
  - 音频混音: `mix_final_audio()` (L751), `normalize_audio_loudness()` (L812)
  - 质量校验: `validate_output()` (L839)
  - 元数据生成: `generate_publish_metadata()` (L886)
  - 图片生成: `generate_multi_images()` (L937)
  - 视频合成: `assemble_pro_video()` (L973)

---

## 2. TTS 模块审计 (MiMo 集成关键)

### 2.1 当前 TTS 架构

**文件位置**: `engine.py` L518-L721

**核心函数**:
- `_cosyvoice_model_for_voice(voice_name)` L518-L528: 音色名 -> CosyVoice 模型名映射 (v1/v2/v3-flash/clone)
- `_synthesize_cosyvoice(text, output_path, speed)` L535-L555: 底层 CosyVoice SDK 调用
- `generate_audio(text, output_dir, theme_name)` L557-L721: **主入口**，含词法解析 -> 区块组装 -> 韵律应用 -> TTS 调用 -> 音频拼接 -> 字幕导出

**Fallback 链实现** (L637, L663-L676):
```python
cosyvoice_disabled = False  # 局部变量管理全局状态
...
if use_pro_voice and not cosyvoice_disabled:
    try:
        await _synthesize_cosyvoice(sub_text_clean, temp_path, speed=speed)
    except Exception as cosyvoice_err:
        if "AllocationQuota" in err_str:
            cosyvoice_disabled = True  # 会话级全局禁用
        await edge_tts.Communicate(...)  # 降级到 edge-tts
else:
    await edge_tts.Communicate(...)  # 直接用 edge-tts
```

### 2.2 MiMo 集成切入点分析

**CRITICAL: TTS 调用逻辑耦合在 generate_audio() 中**
- 问题: TTS 选择、调用、fallback 逻辑全部嵌入在 164 行的 `generate_audio()` 函数中
- 影响: 无法独立测试 TTS 模块；添加新 TTS 引擎必须修改核心音频流水线
- MiMo 集成需要: 在 L663 的 if 分支中再加一层 MiMo 调用 -> 进一步增加函数复杂度
- 建议: **必须先提取 TTS 抽象层**，再集成 MiMo

**HIGH: 缺少 TTS 抽象层**
- 当前: 直接调用 `edge_tts.Communicate` 和 `_synthesize_cosyvoice`
- 问题: 没有统一的 TTS 接口，每添加新引擎都需要修改 `generate_audio()` 多处代码
- MiMo 影响: 如果不重构，MiMo 集成会变成又一个 if/else 分支嵌套

**MEDIUM: 全局状态管理简陋**
- 位置: L637 `cosyvoice_disabled = False`
- 问题: 用局部变量管理全局状态，无法跨会话持久化
- MiMo 影响: MiMo 也需要类似的 quota 用尽禁用逻辑，两个独立变量会互相干扰

### 2.3 MiMo 集成建议架构

```
tts_engine.py (新增)
+-- BaseTTSEngine (抽象基类)
|   +-- synthesize(text, output_path, speed, voice) -> bool
|   +-- is_available() -> bool
+-- MiMoTTSEngine(BaseTTSEngine)
|   +-- _synthesize_preset()
|   +-- _synthesize_voicedesign()
+-- CosyVoiceTTSEngine(BaseTTSEngine)
|   +-- _cosyvoice_model_for_voice()
+-- EdgeTTSEngine(BaseTTSEngine)
+-- TTSManager
    +-- engines: list[BaseTTSEngine]
    +-- synthesize_with_fallback(text, output_path, speed)
    +-- _failed_engines: set  # 替代 cosyvoice_disabled 局部变量
```

---

## 3. config.py 审计

### 3.1 结构分析

**文件位置**: `/Users/motou/Desktop/bedtime_story_agent/config.py` (409行)

| Section | 行范围 | 占比 | 职责 |
|---------|--------|------|------|
| 环境变量加载 | L1-L40 | 10% | .env 读取、代理清理、SSL 修复 |
| API 配置 | L42-L75 | 8% | DashScope/文本/图片/TTS API key 和参数 |
| edge-tts 音色表 | L77-L100 | 6% | 音色映射、主题到音色的对应 |
| TTS 标记规范 | L102-L125 | 6% | LLM 写稿时须遵守的语音合成标记 |
| **主题定义** | **L127-L367** | **60%** | 13 个主题，每个 8 字段 |
| 主题分类 | L370-L394 | 6% | 4 大分类 |
| 韵律曲线 | L400-L409 | 2% | 唯一曲线配置 |

### 3.2 发现

**MEDIUM: 主题配置过于庞大 (60% 占比)**
- 问题: THEMES 字典包含 13 个主题，每个主题 8 个字段（story_prompt, image_prompt, bgm_file, category, pain_point, technique, search_keywords, ideal_duration_min, emotional_target）
- 影响: config.py 臃肿；添加新主题需要修改核心配置文件；不利于非技术人员编辑
- 建议: 迁移到 `themes.json` 或 `themes/` 目录

**LOW: 缺少 MiMo 相关配置**
- 当前只有 CosyVoice 和 edge-tts 配置
- 集成 MiMo 需要添加:
  - `MI_API_KEY` / `MIMO_BASE_URL`
  - `MIMO_VOICES` (预置音色映射)
  - `MIMO_HOST_CONFIGS` (Voice Design 描述)

---

## 4. 测试覆盖审计

### 4.1 测试文件统计

| 测试文件 | 行数 | 覆盖模块 | 覆盖质量 |
|----------|------|----------|----------|
| test_cosyvoice_synthesize.py | 113 | `engine._synthesize_cosyvoice` | 高 (5 个用例，mock SDK) |
| test_prosody.py | 176 | `prosody.py` 全模块 | 高 (曲线插值、阶段标记、内联标记) |
| test_publish_helpers.py | 357 | publish.py 辅助函数 | 中 |
| test_cosyvoice_live.py | 71 | CosyVoice 集成 | 低 (需 API Key，`RUN_COSYVOICE_LIVE=1`) |
| stub_engine_imports.py | 116 | (测试基础设施) | 高 (可复用的 mock 框架) |
| asyncio_compat.py | 21 | (测试基础设施) | 高 |
| **合计** | **854** | | |

### 4.2 测试覆盖缺口

**CRITICAL: engine.py 核心函数无测试**
- `generate_audio()` - TTS 主流水线 (164 行)，0% 测试覆盖
- `generate_story()` - 故事生成 3-pass LLM (110 行)，0% 测试覆盖
- `mix_final_audio()` - 音频混音 (60 行)，0% 测试覆盖
- `generate_publish_metadata()` - 元数据生成 (47 行)，0% 测试覆盖

**HIGH: batch.py 无测试**
- 282 行的批量生产主入口，完全无测试覆盖

**MEDIUM: 测试基础设施质量好**
- `stub_engine_imports.py` 提供了完整的 mock 框架
- 测试模式: `unittest.mock` + `patch`，不依赖外部 API
- 可复用性高，新模块测试可直接借鉴

---

## 5. 依赖管理审计

### 5.1 requirements.txt 分析

```
moviepy>=1.0.3,<2.0      # OK: pinned to v1 (v2 removes moviepy.editor)
dashscope>=1.14.0         # CosyVoice + Wan2.x + Qwen
edge-tts>=6.1.0           # TTS 兜底
yt-dlp>=2024.0.0          # YouTube BGM 下载
Pillow>=9.0.0             # 图片处理
rich>=13.0.0              # 终端 UI
openai>=1.0.0             # LLM API (also MiMo-compatible)
numpy>=1.20.0             # 数值计算
requests>=2.28.0          # HTTP
mutagen>=1.47.0           # MP3 元数据
pyloudnorm>=0.1.0         # LUFS 响度归一化
soundfile>=0.12.0         # 音频文件 I/O
```

### 5.2 发现

**HIGH: 缺少 MiMo 依赖但兼容**
- MiMo API 是 OpenAI-compatible，`openai>=1.0.0` 已在依赖中
- 可能需要确认最低版本是否支持 MiMo 的自定义参数

**MEDIUM: 大部分依赖版本约束过松**
- 仅 `moviepy` 有上限 (`<2.0`)
- 其他全部 `>=` 无上限，未来可能破坏兼容性
- 建议: 对 `dashscope`, `edge-tts` 添加上限

**LOW: 缺少开发依赖文件**
- 缺少 `requirements-dev.txt` 或 `[dev]` extras
- 测试用 `unittest` (标准库)，无需额外依赖，但可考虑 pytest

---

## 6. 代码异味

### 6.1 重复代码

**MEDIUM: BGM 路径查找逻辑重复**
- 位置 1: `engine.py` L764-L769 (`mix_final_audio`)
- 位置 2: `engine.py` L981-L992 (`assemble_pro_video`)
- 完全相同的 `for candidate in (f"assets/bgm/{bgm_filename}", f"assets/{bgm_filename}")` 模式
- 建议: 提取为 `_resolve_bgm_path(filename) -> str | None`

**LOW: LLM 调用模式部分重复**
- 已有 `_llm_call()` 封装 (L281-L290)
- 但 L381 (`_generate_chapter_titles`) 和 L910 (`generate_publish_metadata`) 未使用此封装
- 建议: 统一使用 `_llm_call()`

### 6.2 过长函数

| 函数 | 行数 | 位置 | 严重度 |
|------|------|------|--------|
| `generate_audio()` | 164 | L557-L721 | CRITICAL |
| `generate_story()` | 110 | L252-L361 | HIGH |
| `assemble_pro_video()` | 63 | L973-L1035 | MEDIUM |
| `generate_soothing_noise()` | 51 | L465-L515 | LOW |

`generate_audio()` 承担了 6 个不同职责:
1. 词法解析 (L567-L607, 40 行)
2. 区块组装 (L609-L629, 20 行)
3. 韵律应用 (L632, 1 行，调用 prosody.py)
4. TTS 合成循环 (L635-L699, 64 行)
5. 音频拼接 (L701-L715, 14 行)
6. 字幕导出 (L718-L721, 3 行)

### 6.3 过深嵌套

**MEDIUM: TTS fallback 嵌套 (4 层)**
- 位置: `engine.py` L663-L676
```python
for i, block in enumerate(blocks):         # L639 - for
    if use_pro_voice and not cosyvoice_disabled:  # L664 - if
        try:                                     # L665 - try
            await _synthesize_cosyvoice(...)
        except Exception as cosyvoice_err:       # L666 - except
            ...
```
- MiMo 集成后会变成 5 层 (再加一层 if mimo)
- 建议: 使用策略模式或 early return

### 6.4 异常处理问题

**HIGH: 裸 except 滥用**
- `engine.py` L247: `except: return None` (select_best_bgm)
- `engine.py` L1030: `except: break` (assemble_pro_video 字幕渲染)
- 吞掉所有异常，包括 `KeyboardInterrupt`, `SystemExit`

**MEDIUM: 异常信息静默丢弃**
- `engine.py` L462: `except Exception: return 75, ""` (_evaluate_story)
- API 失败时返回默认值 75 分，无日志

---

## 7. MiMo 集成准备度评估

### 7.1 可复用组件

| 组件 | 位置 | 复用性 | 改造难度 |
|------|------|--------|----------|
| ProsodyCurve + apply_curve_to_blocks | prosody.py 全文 | 高 | 低 - 只需添加 `prosody_to_mimo_style()` |
| 音频后处理 (fade/volume/concat) | engine.py L681-L715 | 高 | 无需改造 |
| 字幕导出 | engine.py L724-L745 | 高 | 无需改造 |
| 测试基础设施 (stub + asyncio_compat) | tests/ | 高 | 可直接复用 |
| API_CONFIG / THEME_VOICE_MAP | config.py | 高 | 需扩展 |

### 7.2 需要新增的模块

1. **mimo_tts.py** (~150 行): MiMo API 调用封装 (preset + voicedesign)
2. **tts_engine.py** (~200 行): TTS 抽象层 + TTSManager
3. **config.py 补充** (~30 行): MiMo 配置项

### 7.3 需要修改的模块

1. **engine.py** `generate_audio()`: 用 TTSManager 替换内联的 TTS 逻辑 (~50 行改动)
2. **prosody.py**: 添加 `prosody_to_mimo_style()` (~30 行)
3. **requirements.txt**: 确认 openai 版本兼容 (0-1 行改动)

---

## 8. 优先级排序

| 优先级 | 任务 | 严重度 | 说明 |
|--------|------|--------|------|
| P0 | 提取 TTS 抽象层 (tts_engine.py) | CRITICAL | MiMo 集成前提，否则无法干净插入 |
| P0 | 创建 mimo_tts.py | CRITICAL | MiMo 集成本体 |
| P0 | 添加 MiMo 配置到 config.py | HIGH | 所有模块需要读取 |
| P1 | 修改 engine.py 接入 TTSManager | HIGH | 替换内联 TTS 逻辑 |
| P1 | 修改 prosody.py 添加 MiMo 映射 | MEDIUM | prosody -> MiMo style 标签 |
| P1 | 添加 TTS 模块测试 | HIGH | 确保 fallback 链正确 |
| P2 | 提取 BGM 路径查找工具函数 | MEDIUM | 减少重复代码 |
| P2 | 拆分 engine.py (故事/音频/视频/元数据) | HIGH | 降低复杂度 |
| P2 | 提取主题配置到 themes.json | MEDIUM | 降低 config.py 臃肿度 |
| P3 | 拆分 publish.py (4805行) | CRITICAL | 长期技术债务 |
| P3 | 改进异常处理 (消除裸 except) | MEDIUM | 代码质量 |

---

## 9. 工作量评估

### MiMo 集成 (P0+P1)

| 任务 | 预计工时 | 依赖 |
|------|----------|------|
| 创建 tts_engine.py (抽象层) | 4h | 无 |
| 创建 mimo_tts.py | 3h | tts_engine.py |
| 修改 config.py | 0.5h | 无 |
| 修改 engine.py 接入 TTSManager | 2h | tts_engine.py |
| 修改 prosody.py | 1h | 无 |
| 添加测试 | 3h | mimo_tts.py, tts_engine.py |
| **MiMo 集成总计** | **~13.5h** | |

### 后续优化 (P2+P3)

| 任务 | 预计工时 |
|------|----------|
| 拆分 engine.py | 8h |
| 拆分 publish.py | 6h |
| 提取主题配置 | 2h |
| 改进异常处理 | 3h |
| **优化总计** | **~19h** |

---

> 审计完成时间: 2026-05-01
> 状态: COMPLETE
> 下一步: 通知 team-lead 审批，审批通过后进入 Ta2 (重构方案详细设计)
