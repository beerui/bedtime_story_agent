# 调研: prosody-MiMo 映射 - 计划

> 智能体: researcher-technical
> 状态: pending
> 创建: 2026-05-01

## 调研问题

1. 现有 prosody.py 的 speed/volume/pause 参数如何映射到 MiMo 风格标签？
2. MiMo 的导演模式指令能否表达 prosody curve 的渐变效果？
3. 阶段标记（引入/深入/尾声）对应什么 MiMo 风格？
4. 内联标签（[慢速]/[轻声]/[极弱]）如何转换为 MiMo 音频标签？

## 方法

- [ ] 1. 读 prosody.py，分析 PROSODY_CURVES 配置和 curve 映射逻辑
- [ ] 2. 读 engine.py 中 prosody 相关的 TTS 调用逻辑
- [ ] 3. 分析 MiMo 风格标签和导演模式的控制能力
- [ ] 4. 设计映射方案
- [ ] 5. 将结论写入 findings.md
- [ ] 6. 更新根索引 + 通知 team-lead

## 范围

- 范围内：prosody 参数→MiMo 风格标签的映射方案
- 范围外：实际代码实现（由 backend-dev 负责）
