# Episode 页面适配 MiMo - 发现

## 站点结构分析

### episode 页面模板关键区域

1. **头部信息区** (L414-418): 返回链接 + theme-badge + h1 标题 + meta + tags
2. **场景图** (L419): `.scene-hero` 带图片
3. **音频播放器** (L421-64): `.player` 含倍速/定时器/audio controls/分享/下载
4. **章节导航** (L466): `.chapters` 按 phase 分段
5. **心理锚点** (L468): `.tech-badge` 含感受/技术/状态三行
6. **摘要** (L470): `.summary`
7. **正文** (L472-502): `article.transcript` 含 phase h2 + p 段落
8. **上下集导航** (L504): `.ep-nav`
9. **支持/推荐** (L509-551): support tiles + affiliates + related

### 数据来源
- `episodes.json` 提供所有结构化数据
- episode HTML 由 `publish.py` 生成
- 当前无 narrator/voice/tts_engine 字段

### 需要适配的位置
- 头部信息区：新增主播信息展示
- 标签区：新增音色/风格标签
- 心理锚点区：可能需要新增 TTS 引擎信息
- 播放器：确认 wav 格式兼容性

### 音频格式兼容性
- 当前全部为 mp3
- MiMo 输出 wav
- `<audio>` 标签原生支持 wav，无需额外处理
- 但 wav 文件体积较大，可能需要后处理转 mp3 或考虑 streaming
