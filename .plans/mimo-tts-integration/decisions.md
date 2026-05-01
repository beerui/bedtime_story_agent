# MiMo-V2.5-TTS 集成 - 架构决策记录

> 记录每个决策及其理由。

---

## D1: TTS 引擎优先级

- 日期: 2026-05-01
- 决策: MiMo → CosyVoice → edge-tts 三级 fallback
- 理由: MiMo 免费且质量高（V2.5 支持 Voice Design + 风格标签），作为首选。CosyVoice 作为备选。edge-tts 作为最终兜底。
- 考虑过的替代方案: 仅用 MiMo 不做 fallback（风险太高）

## D2: MiMo 模型选择

- 日期: 2026-05-01
- 决策: 主用 mimo-v2.5-tts（预置音色）+ mimo-v2.5-tts-voicedesign（主播定制）
- 理由: Voice Clone 暂不需要，预置音色 + Voice Design 足够覆盖多主播场景
- 考虑过的替代方案: 全部用 Voice Design（成本高、延迟大）

## D3: 多主播方案

- 日期: 2026-05-01
- 决策: 每个主题/系列绑定一个 Voice Design 描述 + 预置音色 fallback
- 理由: Voice Design 可以为每个主题定制声线（如"午夜慢车"配慵懒磁性男声），预置音色作为降级
- 考虑过的替代方案: 全部用预置音色（差异化不足）
