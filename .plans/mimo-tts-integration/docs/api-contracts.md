# MiMo-V2.5-TTS 集成 - API 契约

> MiMo API 接口定义和内部 TTS 抽象层接口。
> 维护者：backend-dev

## 外部 API: MiMo TTS

### POST https://api.xiaomimimo.com/v1/chat/completions

**字段表**：

| 字段 | 类型 | 必填 | 单位/格式 | 描述 |
|------|------|------|-----------|------|
| model | string | 是 | 枚举 | `mimo-v2.5-tts` / `mimo-v2.5-tts-voicedesign` / `mimo-v2.5-tts-voiceclone` |
| messages | array | 是 | — | 消息数组 |
| messages[].role | string | 是 | 枚举 | `user` (风格指令) / `assistant` (待合成文本) |
| messages[].content | string | 是 | — | 消息内容 |
| audio.format | string | 是 | 枚举 | `wav` (非流式) / `pcm16` (流式) |
| audio.voice | string | 条件 | — | 预置音色 ID (preset 模型必填) / base64 音频 (voiceclone) |
| stream | boolean | 否 | — | 是否流式，默认 false |

**Request Headers**：

| Header | 值 | 描述 |
|--------|---|------|
| api-key | {MI_API_KEY} | 认证密钥 |
| Content-Type | application/json | — |

**Response (非流式)**：

| 字段 | 类型 | 描述 |
|------|------|------|
| choices[0].message.audio.data | string | base64 编码的音频数据 |

## 内部接口: mimo_tts.py

### synthesize_mimo(text, output_path, voice=None, style=None, model=None)

统一 TTS 入口。

**参数**：

| 字段 | 类型 | 必填 | 描述 |
|------|------|------|------|
| text | str | 是 | 待合成文本 |
| output_path | str | 是 | 输出音频文件路径 (.wav) |
| voice | str | 否 | 预置音色 ID 或 Voice Design 描述。默认使用 config 中的主题映射 |
| style | str | 否 | 风格标签 (如 "温柔 慵懒") 或导演模式指令 |
| model | str | 否 | 指定模型。默认自动选择（有 voice 用 preset，否则用 voicedesign） |

**返回**: bool (成功/失败)

**异常**: 不抛异常，失败时返回 False 供 fallback 逻辑处理
