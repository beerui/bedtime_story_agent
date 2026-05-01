# MiMo-V2.5-TTS 集成 - 系统不变量

> 不可违反的系统边界。违反其中任何一条 = CRITICAL Bug。

## 音频质量边界

- INV-1: TTS 输出必须为有效音频文件（wav/mp3），采样率 >= 16kHz — 状态：无测试
- INV-2: 单段 TTS 合成超时 30 秒必须触发 fallback — 状态：无测试
- INV-3: MiMo 失败时必须无感降级到 CosyVoice，用户不可感知中断 — 状态：无测试

## 降级规则

- INV-4: Fallback 链顺序固定：MiMo → CosyVoice → edge-tts，不可跳过 — 状态：无测试
- INV-5: CosyVoice 额度耗尽后全局禁用 CosyVoice（现有行为），直接跳到 edge-tts — 状态：已有测试
- INV-6: MiMo 额度耗尽（如未来开始计费）应同样全局禁用 — 状态：无测试

## 数据隔离

- INV-7: API Key 不可硬编码在源码中，必须从 .env 读取 — 状态：人工检查
- INV-8: 音频临时文件合成后必须清理 — 状态：无测试

## 接口契约

- INV-9: MiMo API 调用必须使用 OpenAI-compatible SDK，不可直接 requests — 状态：人工检查
- INV-10: 风格标签必须与 prosody curve 参数一致（同一段落不可矛盾） — 状态：无测试
