# researcher-technical - 发现索引

> 纯索引——每个条目应简短（Status + Report 链接 + Summary）。

---

## T0a: prosody-MiMo 映射调研

**Status**: DONE
**Report**: [research-prosody-mimo/findings.md](research-prosody-mimo/findings.md)
**Summary**: Prosody curve 的 speed/volume/pause 参数可通过 MiMo 两层控制机制（user content 风格指令 + assistant content 音频标签）完整表达。推荐六段式分段方案：按 progress 将脚本分为 6 段，每段约 15-20%，段边界对齐阶段标记。每段使用不同的 user content 风格描述，段内通过音频标签微调。需在 prosody.py 新增 `to_mimo_styles()` 方法，在 config.py 新增风格模板配置。
