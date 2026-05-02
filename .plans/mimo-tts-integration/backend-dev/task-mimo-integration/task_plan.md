# MiMo TTS API 集成 - 任务计划

> 所属智能体: backend-dev
> 状态: IN_PROGRESS
> 创建: 2026-05-01
> 更新: 2026-05-02
> 预计工作量: ~13.5h

## 目标

提取 TTS 抽象层 + 创建 MiMo TTS 模块 + 接入 TTSManager，实现 MiMo → CosyVoice → edge-tts 三级 fallback。

## 架构设计（来自 architect 审计）

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

## 详细步骤

### Phase 1: TTS 抽象层（4h）

- [ ] 1.1 创建 `tts_engine.py`，定义 `BaseTTSEngine` 抽象基类
  - 接口：`synthesize(text, output_path, speed, voice) -> bool`
  - 接口：`is_available() -> bool`
  - 接口：`engine_name() -> str`
- [ ] 1.2 实现 `CosyVoiceTTSEngine(BaseTTSEngine)`
  - 迁移 `_synthesize_cosyvoice()` 逻辑
  - 迁移 `_cosyvoice_model_for_voice()` 逻辑
- [ ] 1.3 实现 `EdgeTTSEngine(BaseTTSEngine)`
  - 迁移 edge-tts 调用逻辑
- [ ] 1.4 实现 `TTSManager`
  - `engines: list[BaseTTSEngine]` — 引擎列表（按优先级排序）
  - `synthesize_with_fallback(text, output_path, speed) -> bool` — 自动 fallback
  - `_failed_engines: set` — 替代 `cosyvoice_disabled` 局部变量

### Phase 2: MiMo TTS 模块（3h）

- [ ] 2.1 创建 `mimo_tts.py`，实现 `MiMoTTSEngine(BaseTTSEngine)`
  - 使用 openai SDK，`base_url=MI_BASE_URL`
  - 支持 `mimo-v2.5-tts`（预置音色）
  - 支持 `mimo-v2.5-tts-voicedesign`（Voice Design）
- [ ] 2.2 实现 `_synthesize_preset(text, output_path, voice)`
  - 预置音色：冰糖/茉莉/苏打/白桦
- [ ] 2.3 实现 `_synthesize_voicedesign(text, output_path, voice_description)`
  - Voice Design：自然语言描述声线
- [ ] 2.4 实现统一入口 `synthesize(text, output_path, speed, voice)`
  - 根据 voice 类型自动选择 preset/voicedesign

### Phase 3: 配置与集成（2.5h）

- [ ] 3.1 更新 `config.py`，添加 MiMo 配置
  - `MI_API_KEY` / `MI_BASE_URL` / `MI_TEXT_MODEL`
  - `MIMO_PRESET_VOICES` — 预置音色映射
  - `THEME_MIMO_VOICE_MAP` — 主题→音色映射
- [ ] 3.2 修改 `engine.py`，用 `TTSManager` 替换内联 TTS 逻辑
  - 删除 `cosyvoice_disabled` 局部变量
  - 删除内联的 TTS 调用代码
  - 调用 `TTSManager.synthesize_with_fallback()`
- [ ] 3.3 修改 `prosody.py`，添加 `prosody_to_mimo_style()` 函数
  - 将 speed/volume/pause 曲线转换为 MiMo 风格标签

### Phase 4: 测试（3h）

- [ ] 4.1 创建 `tests/test_tts_engine.py`
  - 测试 BaseTTSEngine 接口
  - 测试 TTSManager fallback 逻辑
  - 测试 CosyVoiceTTSEngine 迁移
  - 测试 EdgeTTSEngine 迁移
- [ ] 4.2 创建 `tests/test_mimo_tts.py`
  - 测试 MiMoTTSEngine（mock API response）
  - 测试预置音色模式
  - 测试 Voice Design 模式
  - 测试 fallback 行为
- [ ] 4.3 更新 `scripts/run_ci.py`，添加新测试到 CI

## 涉及文件

| 文件 | 操作 | 说明 |
|------|------|------|
| `tts_engine.py` | 新建 | TTS 抽象层 + TTSManager |
| `mimo_tts.py` | 新建 | MiMo TTS 模块 |
| `config.py` | 修改 | 添加 MiMo 配置 |
| `engine.py` | 修改 | 用 TTSManager 替换内联 TTS |
| `prosody.py` | 修改 | 添加 prosody_to_mimo_style() |
| `tests/test_tts_engine.py` | 新建 | TTS 抽象层测试 |
| `tests/test_mimo_tts.py` | 新建 | MiMo TTS 测试 |
| `scripts/run_ci.py` | 修改 | 添加新测试 |

## 依赖

- ✅ T0a: prosody-MiMo 映射调研（已完成）
- ✅ Ta1: 代码库审计（已完成）
- ✅ MiMo API 文档：`.plans/mimo-tts-integration/docs/api-contracts.md`
- ✅ 架构设计：`.plans/mimo-tts-integration/architect/task-codebase-audit/findings.md`

## 验收标准

1. `python3 -m unittest tests.test_tts_engine tests.test_mimo_tts -v` — 全部通过
2. `python3 scripts/run_ci.py` — CI 通过
3. MiMo TTS 合成成功（需有效 API Key）
4. Fallback 链正常工作：MiMo 失败 → CosyVoice → edge-tts

## 审查预期

完成后需请求 reviewer 审查，重点：
- RD-1: 音频质量（MiMo 合成是否自然）
- RD-2: 容错与降级（fallback 链是否可靠）
- RD-3: 代码可测试性（TTS 模块是否可 mock）
