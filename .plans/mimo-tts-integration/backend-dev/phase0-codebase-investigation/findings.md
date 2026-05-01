# Phase 0: 代码库调研 — 详细发现

## 1. 现有 TTS 实现 (engine.py)

### 1.1 CosyVoice 合成 (`_synthesize_cosyvoice`, L535-555)

- **接口**: `async _synthesize_cosyvoice(text, output_path, speed=0.8)`
- **SDK**: dashscope.audio.tts_v2.SpeechSynthesizer
- **模型路由**: `_cosyvoice_model_for_voice(voice_name)` 根据音色名自动选择 v1/v2/v3-flash/clone
- **速度控制**: `speech_rate=speed` 参数，float 类型
- **输出**: 直接写 wav/mp3 二进制数据

### 1.2 TTS Fallback 链 (`generate_audio`, L557-721)

当前是**两级降级**:
```
CosyVoice → edge-tts
```

关键代码在 L663-678:
```python
if use_pro_voice and not cosyvoice_disabled:
    try:
        await _synthesize_cosyvoice(sub_text_clean, temp_path, speed=speed)
    except Exception as cosyvoice_err:
        if "AllocationQuota" in err_str:
            cosyvoice_disabled = True  # 全局禁用
        await edge_tts.Communicate(...).save(temp_path)
else:
    await edge_tts.Communicate(...).save(temp_path)
```

**插入 MiMo 的最佳位置**: L664 的 `if use_pro_voice` 分支内，在 CosyVoice 之前加 MiMo 尝试。

### 1.3 音频后处理

- 每段 TTS 后: `AudioFileClip` + `volumex(vol)` + `audio_fadein/fadeout` (进度越大 fade 越长)
- 全局: `concatenate_audioclips` → `write_audiofile`
- BGM 混音: `mix_final_audio` (L751-809)
- 响度归一化: `audio_fx.normalize_mp3` (LUFS -22)

## 2. 配置系统 (config.py)

### 2.1 TTS 相关配置

| 配置项 | 当前值 | MiMo 扩展需求 |
|--------|--------|---------------|
| `API_CONFIG["cosyvoice_api_key"]` | DashScope key | 新增 `MI_API_KEY` |
| `API_CONFIG["tts_voice"]` | `longyue_v3` | 新增 MiMo voice 映射 |
| `EDGE_TTS_DEFAULT` | `zh-CN-XiaoxiaoNeural` | 不变 |
| `THEME_VOICE_MAP` | 10个主题→edge-tts音色 | 需扩展为 MiMo Voice Design 映射 |

### 2.2 代理清除逻辑

L28-32: 如果 `PROXY_BASE_URL` 包含 "dashscope"，会清除代理环境变量。
MiMo API (api.xiaomimimo.com) 不受此影响，但需注意如果代理存在可能干扰 MiMo 请求。

## 3. Prosody Curve 系统 (prosody.py)

### 3.1 核心数据结构

`ProsodyCurve` 持有三条分段线性曲线:
- `speed`: 0.0→1.0 映射为 1.0→0.55 (越来越慢)
- `volume`: 0.0→1.0 映射为 1.0→0.3 (越来越轻)
- `pause`: 0.0→1.0 映射为 0.3→2.0s (停顿越来越长)

### 3.2 阶段标记与进度映射

`PHASE_ANCHORS`: 引入=0.0, 深入=0.3, 尾声=0.7
`_build_progress_map`: 用阶段锚点做非线性进度重映射

### 3.3 MiMo 风格标签映射方案 (待 researcher-technical 确认)

需要将 prosody curve 参数映射为 MiMo 的 style text (放在 user message content 中):

| Prosody 状态 | speed | volume | 建议 MiMo 风格标签 |
|-------------|-------|--------|-------------------|
| 进度 0-30% (引入) | 1.0→0.9 | 1.0→0.95 | "自然 平静" |
| 进度 30-70% (深入) | 0.9→0.75 | 0.95→0.6 | "轻柔 缓慢 低语" |
| 进度 70-100% (尾声) | 0.75→0.55 | 0.6→0.3 | "极轻 极慢 催眠" |

内联标签 `[慢速]`/`[轻声]`/`[极弱]` 作为 multiplicative modifier，需要转换为 MiMo 风格标签的加强版。

## 4. 集成方案设计 (初步)

### 4.1 新增文件: `mimo_tts.py`

```python
async def synthesize_mimo(text, output_path, voice=None, style=None, model=None) -> bool:
    """统一 MiMo TTS 入口。失败返回 False，不抛异常。"""
```

使用 openai SDK:
```python
client = OpenAI(api_key=MI_API_KEY, base_url="https://api.xiaomimimo.com/v1")
response = client.chat.completions.create(
    model="mimo-v2.5-tts-voicedesign",
    messages=[
        {"role": "user", "content": style or "温柔 平静"},
        {"role": "assistant", "content": text},
    ],
    audio={"format": "wav", "voice": voice},
)
audio_data = base64.b64decode(response.choices[0].message.audio.data)
```

### 4.2 engine.py 修改点

1. **L557 `generate_audio`**: 在 fallback 链最前面插入 MiMo 尝试
2. **L664**: 修改为 MiMo → CosyVoice → edge-tts 三级降级
3. **新增**: `_build_mimo_style(progress, block)` 根据 prosody progress 生成 style text

### 4.3 config.py 扩展

```python
# MiMo TTS 配置
"mi_api_key": os.getenv("MI_API_KEY", "").strip(),
"mi_base_url": os.getenv("MI_BASE_URL", "https://api.xiaomimimo.com/v1").strip(),

# 主题 → MiMo Voice Design 描述
MIMO_VOICE_DESIGNS = {
    "午夜慢车": "低沉磁性的男声，带有深夜独白的孤独感",
    "雨夜山中小屋": "温柔的女声，像耳边低语，带有雨夜的慵懒",
    ...
}
```

## 5. 待确认项 (等待 T0a 结论)

- [ ] MiMo style text 的最佳格式（是关键词还是自然语言描述？）
- [ ] MiMo 对速度/音量的精确控制能力（是否支持 SSML 或类似标记？）
- [ ] Voice Design 的调用延迟和稳定性
- [ ] MiMo 流式 vs 非流式的选择（非流式更简单，但延迟高）
