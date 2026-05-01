# 调研: prosody-MiMo 映射 - 搜索日志

> 记录搜索了什么、找到了什么。

---

## 2026-05-01 调研过程

### Step 1: 读取 prosody.py

- **文件**: `/Users/motou/Desktop/bedtime_story_agent/prosody.py` (161 行)
- **发现**:
  - `ProsodyCurve` 类: 分段线性曲线，持有 speed/volume/pause 三条曲线
  - `PHASE_ANCHORS`: 引入=0.0, 深入=0.3, 尾声=0.7
  - `TAG_MULTIPLIERS`: 慢速(0.8x), 轻声(0.5x vol), 极弱(0.7x speed + 0.3x vol)
  - `apply_curve_to_blocks()`: 为每个 speech block 注入 speed/vol/progress
  - `_build_progress_map()`: 用阶段锚点做非线性进度重映射

### Step 2: 读取 config.py PROSODY_CURVES

- **文件**: `/Users/motou/Desktop/bedtime_story_agent/config.py` L402-408
- **发现**:
  - "hypnotic" 曲线: speed 1.0→0.55, volume 1.0→0.3, pause 0.3→2.0s
  - 四个控制点: (0.0, 1.0), (0.3, 0.9), (0.7, 0.75), (1.0, 0.55)

### Step 3: 读取 engine.py TTS 调用逻辑

- **文件**: `/Users/motou/Desktop/bedtime_story_agent/engine.py` L557-721
- **发现**:
  - `generate_audio()` 函数: 核心音频流水线
  - L632: `apply_curve_to_blocks(blocks, curve)` 应用韵律曲线
  - L653-655: 读取 block 的 speed/vol/progress
  - L661: edge-tts rate 映射: `f"{int((speed - 1.0) * 100):+d}%"`
  - L666: CosyVoice: `_synthesize_cosyvoice(text, path, speed=speed)`
  - L684: 音量: `clip.volumex(vol)`
  - L688-689: fade 曲线随 progress 增大

### Step 4: 读取 MiMo API 契约

- **文件**: `.plans/mimo-tts-integration/docs/api-contracts.md`
- **发现**:
  - POST `https://api.xiaomimimo.com/v1/chat/completions`
  - messages[].role: user (风格指令) / assistant (待合成文本)
  - audio.format: wav / pcm16
  - audio.voice: 预置音色 ID 或 base64 音频
  - 内部接口: `synthesize_mimo(text, output_path, voice, style, model)`

### Step 5: 读取 architecture.md

- **文件**: `.plans/mimo-tts-integration/docs/architecture.md`
- **发现**:
  - TTS Fallback 链: MiMo → CosyVoice → edge-tts
  - 数据流: 阶段标记 → prosody curve progress → MiMo 风格标签
  - `prosody.py` 计划新增: `prosody_to_mimo_style()` 方法

### Step 6: 读取 backend-dev 代码库调研

- **文件**: `.plans/mimo-tts-integration/backend-dev/phase0-codebase-investigation/findings.md`
- **发现**:
  - 已有初步映射方案（进度区间→风格标签）
  - 确认插入 MiMo 的最佳位置: L664 的 if 分支前
  - 待确认项: style text 格式、速度/音量精确控制、延迟

### Step 7: 网络搜索 MiMo 风格标签文档

- **尝试**: WebSearch "MiMo-V2.5-TTS 风格标签 导演模式"
- **结果**: 未获取到有效结果（搜索工具限制）
- **替代**: 基于 api-contracts.md 和用户提供的控制要点推断

### Step 8: 综合分析与方案设计

- 基于所有信息设计了六段式映射方案
- 核心思路: progress 区间 → user content 风格描述 + assistant content 音频标签
- 输出: research-prosody-mimo/findings.md
