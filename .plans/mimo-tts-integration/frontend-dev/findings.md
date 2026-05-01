# frontend-dev - 发现索引

> 纯索引——每个条目应简短（Status + Report 链接 + Summary）。

---

## [2026-05-01] Phase 0: 站点结构熟悉

**Status**: 完成
**范围**: site/ 目录全面扫描

### 站点总体结构

```
site/
├── index.html          # 首页（119KB，含全部 22 期 episode 卡片 + 内联 CSS/JS）
├── episodes/           # 63 个文件 = 18 个主题 HTML + 对应 .txt + .chapters.json
├── theme/              # 18 个主题页（按主题聚合 episodes）
├── category/           # 4 个分类页（nature_relax, clinical_technique, emotional_resonance, zeitgeist_2026）
├── audio/              # 22 个 .mp3 音频文件
├── scenes/             # 场景图 .png
├── covers/             # 封面图
├── og/                 # Open Graph 图片
├── icons/              # PWA 图标
├── feed/               # 分类 RSS feed
├── share/              # 分享文本
├── episodes.json       # 全量 episode 元数据（结构化 JSON）
├── feed.xml            # Podcast RSS 2.0
├── about.html / privacy.html / terms.html / faq.html / stats.html / themes.html
├── manifest.webmanifest / sw.js / robots.txt / sitemap.xml
└── podcast-cover.png
```

### Episode 数据模型（episodes.json）

每个 episode 包含：
- `id` — 唯一标识，格式 `Batch_YYYYMMDD_HHMMSS_主题名`
- `title`, `theme`, `category`, `pain_point`, `technique`, `emotional_target`
- `description`, `tags[]`, `duration_sec`, `word_count`, `published_at`
- `page_url`, `audio_url`, `transcript_url`
- `chapters[]` — 章节信息 `{title, phase, start_sec, end_sec}`

**关键发现**: 当前数据模型中 **没有** 主播/音色/voice 相关字段。这正是 T1c 需要确定的，也是 T1e 需要适配的。

### Episode 页面模板结构

每个 episode 页面（如 `episodes/Batch_20260417_012110_父母渐老_生命的重量.html`）包含：
1. **头部**: 返回链接 + 主题徽章 + 标题 + 元信息（日期/字数/时长）+ 标签
2. **场景图**: `.scene-hero` 区域
3. **音频播放器**: `.player` 区域
   - 倍速控制按钮（1x/1.25x/1.5x/0.75x 循环）
   - 睡眠定时器
   - `<audio controls>` 原生播放器
   - 分享按钮 + 下载按钮（MP3/文稿）
4. **章节导航**: `.chapters` 区域（可点击跳转）
5. **心理锚点**: `.tech-badge` 区域（感受/技术/状态）
6. **摘要**: `.summary` 区域
7. **正文**: `article.transcript` 区域（含 phase 标记 h2 + 段落）
8. **上下集导航**: `.ep-nav` 区域
9. **支持/广告**: 支持电台 tiles + 联盟推广
10. **相关推荐**: `.related` 区域
11. **JS**: 分享、自动播放下一集、章节导航、播放位置记忆、Media Session API、倍速、睡眠定时

### 样式方案

- **无共享 CSS 文件**: 每个页面全部内联 `<style>`（CSS 变量 + 手写样式）
- **CSS 变量**: `--bg: #06061a; --text: #d4d4e0; --dim: #7a7a9a; --accent: #7c6ff7; --warm: #f0c27f`
- **深色主题**: 暗夜风格，紫色 accent + 暖色 warm
- **响应式**: `@media (max-width: 600px)` 断点

### 构建方式

- `publish.py` 从 `outputs/` 目录读取生产内容，生成 `site/` 下的所有静态页面
- 站点通过 GitHub Pages 部署
- 音频格式: 当前全部为 `.mp3`

### T1e 适配要点（待 T1c 解锁后）

1. **主播信息展示**: 当前页面无主播概念，需要新增 UI 区域
2. **音色/风格标签**: 当前只有内容标签（如"助眠冥想"），需要新增 TTS 音色标签
3. **音频格式兼容**: MiMo 输出 `.wav`，需确认 `<audio>` 标签兼容性（浏览器原生支持 wav）
4. **数据模型扩展**: `episodes.json` 需要新增 `narrator`, `voice`, `tts_engine` 等字段
5. **publish.py 修改**: 构建脚本需要适配新字段，生成新的 UI 元素
