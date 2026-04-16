# Evolution Log

本项目由自治 agent 持续进化。每次改进记录在此，供后续 agent 感知历史、避免重复、持续迭代。

---

## [2026-04-16] SEO 长尾流量：单期页 + sitemap (publish.py)
**动因**: 上一轮把站点做可上线了，但 Google/Bing 只能索引一篇 index.html——音频本身是不可索引的，长尾搜索关键词（"午夜慢车 助眠"、"雨夜山中小屋 冥想"）全部落空。没有自然流量就没有听众，就没有收入
**实现**:
1. `publish.py` 新增 `render_script_html()`：把 `[阶段：X]` → `<h2>`、`[环境音：X]` → `<em class="cue">（X）</em>`、`[停顿]`/`[慢速]`/`[轻声]` 等韵律标记全部剥离，得到适合阅读的纯净 HTML
2. `generate_episode_page()` 为每期产出 `site/episodes/{folder}.html`——包含完整文稿（800+ 字可索引中文内容）、内嵌播放器、分享按钮（Web Share API + 复制链接）、PodcastEpisode JSON-LD schema、canonical URL、OG/Twitter card
3. `generate_sitemap()` 产出 `site/sitemap.xml` 列出首页 + 所有单期页，`generate_robots()` 产出 `site/robots.txt` 指向 sitemap
4. 首页卡片加「阅读全文 →」链接，播放按钮保持原样
**验证**: `python3 publish.py --copy-audio --base-url https://beerui.github.io/bedtime_story_agent` 成功产出 3 个单期页（~9.3KB 各）；PodcastEpisode / canonical / og:type 每页 10+ 个结构化标签；sitemap 列出全 4 个 URL 且使用绝对路径；韵律标记按预期剥离（`[停顿]` 0 处残留，`[环境音：...]` 转为 cue 斜体）
**下一步**:
- 单期页缺少「下一集 / 上一集」导航，算法推荐连播会更长 dwell time
- 没有图片 OG card——目前社交分享缩略图是空的；可用场景图或生成专属封面
- 可以加 Google Analytics / Umami 事件埋点，看哪期留存最长，据此决定后续选题
- 每期文稿底部可再插一个相关推荐区（相似标签的其他期）增加站内链接深度

## [2026-04-16] 变现基础设施 (publish.py + monetization + deploy.sh)
**动因**: 项目有内容但**不能上线**——site/ 里 HTML 用 `../outputs/...` 相对路径，GitHub Pages/Vercel 无法解析；即使能上线，也没有变现接口（打赏/联盟/赞助位），流量无法转化为收入
**实现**:
1. `publish.py --copy-audio` 将 outputs/ 音频拷贝到 site/audio/，生成自包含站点
2. `monetization.example.json` 定义 4 类变现配置：打赏、赞助位、联盟商品网格、会员墙；有 `monetization.json` 时覆盖，无则用示例（UI 上可见骨架）
3. `publish.py` 注入 SEO：OG tags、Twitter Card、JSON-LD PodcastSeries schema、RSS alternate link
4. HTML 增加「支持电台」+「听众的小装备」两个板块，样式跟深色助眠主题统一
5. RSS enclosure 在 `--copy-audio` + `--base-url` 组合下输出绝对 URL（Apple Podcasts 要求）
6. `deploy.sh`：一键 git subtree 推 site/ 到 gh-pages 分支，自动创建 .nojekyll
7. `monetization.json` 加入 .gitignore（避免推广链接泄漏到 public repo）
**验证**: 两种模式均通过——无参数时保留本地预览用的 `../outputs/` 路径；`--copy-audio` 产出 3 个 mp3 (~5.8MB) 到 site/audio/，HTML 里 0 个 `../` 引用，RSS enclosure URL 使用 audio/ 前缀，11 处 support/aff/og/ld 注入点都在
**下一步**:
- monetization.json 的真实链接需要用户配置后才有收入
- deploy.sh 依赖用户已配置 git remote origin，首次使用需人工在 GitHub 开启 Pages + 指向 gh-pages
- 可考虑增加 Google AdSense / 微信小程序码 / 付费会员 paywall 的实现
- RSS 音频大小字段用本地文件大小，如果部署到 CDN 需要重算（通常服务器端 gzip 不影响 mp3 大小）

## [2026-04-16] 播客站点生成器 (publish.py)
**动因**: 生产管线输出完整但缺少分发环节——音频躺在 outputs/ 无法被消费
**实现**: 创建 publish.py，扫描 outputs/ 生成深色主题 HTML 播放器（星空背景、玻璃拟态、睡眠定时器、字幕同步）+ Podcast RSS 2.0 订阅源
**验证**: 成功识别 3 期节目，HTML 和 RSS 均正常生成，本地 HTTP 服务器预览正常
**下一步**: 播放器目前引用本地路径，需要公网部署方案（GitHub Pages / Vercel）  ← ✅ 已在下一次迭代解决

## [2026-04-16] 双耳节拍生成器 (binaural.py)
**动因**: 助眠音频核心差异化不足——韵律弧线控制节奏但缺少脑波层面的干预
**实现**: 创建 binaural.py，生成 Alpha(10Hz)→Theta(6Hz)→Delta(1.5Hz) 渐变双耳节拍，可叠加到已有音频或独立生成；集成到 batch.py --binaural 参数
**验证**: 独立生成 10s 测试音轨正常，增强 4 分钟成品音频正常（1.9MB 输出）
**下一步**: 节拍参数可按主题自动适配（如"深海独潜"用更低载波频率增强沉浸感）

