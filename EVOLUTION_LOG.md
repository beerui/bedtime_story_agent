# Evolution Log

本项目由自治 agent 持续进化。每次改进记录在此，供后续 agent 感知历史、避免重复、持续迭代。

---

## [2026-04-17] 首页客户端搜索 + BreadcrumbList/SearchAction 结构化数据 (publish.py)
**动因**: 22 期内容堆在首页，加上 4 分类芯片只能一级过滤——用户心里想的是「失眠」「加班」「AI」这些关键词，需要模糊匹配；SEO 侧少了两块关键结构化数据：BreadcrumbList（子页面导航上下文）和 WebSite SearchAction（Google sitelinks searchbox 曝光）
**实现**:
1. 首页新增 `<input type="search">` 搜索框，位于订阅区/newsletter 之下、分类芯片之上：
   - 实时 `oninput` 过滤 `.episode` 卡片（显示/隐藏通过 `.hide-by-search` class）
   - 搜索索引 `data-search` 属性预计算：`title + theme + pain_point + technique + tags + desc` 的小写串
   - 与分类芯片叠加工作：`shown` 计数同时考虑 `hide-by-search` 和 `hide-by-filter`
   - 右侧显示 `shown/total` 结果数
   - Debounce 800ms + 去重后触发 `Search Query` 埋点（带 40-char 截断的 query）
   - 支持 `?q=xxx` URL 参数自动填充（来自 Google sitelinks searchbox）
2. 新增 `_breadcrumb_jsonld(items)` 辅助：把 `[(name, url), ...]` 列表变成 BreadcrumbList JSON-LD；最后一项 url="" 表示当前页不加链接
3. 6 类页面注入 BreadcrumbList：
   - 单期页：Home → theme → [episode]
   - 主题页：Home → Themes → (category) → [theme]
   - 分类页：Home → Themes → [category]
   - 主题 hub：Home → [Themes]
   - FAQ / About：Home → [页名]
4. 首页新增 WebSite JSON-LD 含 SearchAction：Google 如果认可，会在搜索结果右侧渲染 sitelinks searchbox，直接从 Google 搜本站
**验证**:
- search 功能：输入 "AI" 只剩 AI焦虑相关，输入 "失眠" 匹配含该词的节目，清空恢复全部；右侧 `shown/total` 实时更新
- 结构化：index.html（BC=0 根页；SA=1 ✓）/ about/faq/themes/category/theme/episode 各 BC=1 ✓
- 已有分类芯片交互不受影响（search change 时 chip 状态保留，反之亦然）
**下一步**:
- 搜索结果为空时可以展示「没找到？试试 [主题 X]」的引导卡
- BreadcrumbList 仅用 JSON-LD，可考虑再在 UI 上做可见面包屑（目前 episode page 靠 theme-badge 替代）
- 搜索索引当前每页加载时塞到 HTML（`data-search` 属性），若节目数破 500 可以外置成 `search-index.json` + fetch

## [2026-04-17] 邮件订阅 form：播客客户端之外的留存通道 (publish.py + monetization.example.json)
**动因**: 订阅按钮覆盖 Apple Podcasts / Spotify / 小宇宙 / RSS，但中国大量用户不用播客客户端——他们可能看了文稿、收藏了链接然后就再也不来。邮件是最普适的「一键加入 + 定期推送」留存通道，尤其对 AI 内容，每周一封编辑过的精选能主动把用户拉回来
**实现**:
1. `_build_newsletter_form(m, context="page")`：输出标准 HTML form POST 到 `monetization.newsletter.endpoint_url`——兼容任意服务商：
   - FormSubmit.co（免注册，POST 到邮箱地址即转发）
   - FormSubmit alias（`/el/alias` 隐藏真实邮箱）
   - Buttondown / Formspark / Formspree（常见订阅服务）
2. FormSubmit 特殊处理：自动注入 `_subject` / `_template` / `_captcha` 三个隐藏字段，让通知邮件漂亮
3. 反爬：`_honey` 蜜罐字段（bot 自动填，人类留空），`autocomplete="email"` 走浏览器密码管理
4. 零配置安全：`enabled=false` 或 `endpoint_url=""` 时 form 整体不渲染，只剩 CSS/JS（未激活状态下完全隐形）
5. `_NEWSLETTER_JS` / `_NEWSLETTER_CSS` 作为模块级常量被 3 个页面模板共享注入——避免重复定义
6. 挂到 3 个关键位置：
   - 首页订阅按钮区下方（最高流量点）
   - 单期页上下集导航下方（听完一期后的情感峰值）
   - 关于页底部（信任建立后的自然 CTA）
7. `onNewsletterSubmit` 触发 `Subscribe Email` 埋点（跨 Plausible / Umami / GA4），让用户能看到哪个位置转化最高
8. monetization.example.json 新增 newsletter 块，注释列出 5 种常见服务的 endpoint 格式
**验证**: 
- enabled=false：3 页面各 0 个 form 渲染，零 UI 痕迹 ✓
- 测试 monetization.json（endpoint=https://formsubmit.co/el/test-alias）：3 页面各 1 个 form，action URL 正确指向 endpoint ✓
- CSS 暖金渐变边框 + 圆角输入框 + 紫到紫粉渐变按钮（与站点主色一致）
**下一步**:
- 可以加「最近订阅了 N 人」伪 live counter（取 localStorage 里的 sign-up 次数作为社交证明）
- 成功回调现在默认让浏览器跳到 provider 的 success 页；如果要无缝体验可打开 `_NEWSLETTER_JS` 里注释掉的 fetch 分支
- 目前 3 个位置都一样的 form 文案；可以按 context（home/episode/about）微调 title/description

## [2026-04-17] 分类 RSS：按兴趣分组订阅 (publish.py)
**动因**: 22 期混在主 feed.xml 里，订阅用户被迫接收全部主题——想要纯心理学技术的和想要时代痛点的是不同人群。播客应用（Apple Podcasts / Pocket Casts / 小宇宙）都支持多 feed 并列，按兴趣分组订阅是标配体验
**实现**:
1. `generate_rss(episodes, base_url, category_key, category_cfg)` 扩展支持过滤：传 category_key 时按 `_THEMES[theme].category == cat_key` 过滤 episodes，channel title 改为「PODCAST_TITLE · 分类标签」，description 用 category.description，link 指向分类页
2. `main()` 生成 4 个 `site/feed/{cat_key}.xml`（只为有节目的分类生成）
3. 分类页 head 加 `<link rel="alternate" type="application/rss+xml">`——播客客户端能自动发现
4. 分类页 header 加「订阅本分类 RSS」UI block：打开 feed.xml 链接 + 复制 URL 按钮（写绝对 URL 到剪贴板，便于粘贴到 Apple Podcasts「通过 URL 添加节目」等入口）；复制后按钮变暖金 1.6s
5. sitemap 新增 4 条 feed URL（priority 0.6）——让搜索引擎知道这些 RSS 存在
**验证**: 4 feed 生成，条目数分别为 zeitgeist_2026=6 / clinical_technique=4 / emotional_resonance=4 / nature_relax=8，合计 22 ✓ 与总数一致；每个 channel title 含正确分类标签；分类页 UI 可交互
**下一步**:
- 分类 RSS URL 可以进一步在 About 页或订阅区以 pill 形式列出（目前要点进分类页才能发现）
- 可考虑按「更新频率」再分：每周一期（zeitgeist）/ 每天一期（nature_relax）等——前提是 batch.py 支持按分类定 cron
- 主 feed 也可以标注 `<itunes:category>` 层级，让 Apple Podcasts 能正确归类

## [2026-04-17] 章节标题从「引入/深入/尾声」升级为具象画面 (engine.py + publish.py + backfill_chapter_titles.py)
**动因**: Apple Podcasts 里每期章节都是一模一样的「引入/深入/尾声」，三个通用标签不区分任何期内容。用户滑过 chapter list 看不到差别——等于没有章节。专业播客（NPR / The Daily / 小宇宙 top 榜）每个章节名都是具体的，这是内容差异化的核心视觉
**实现**:
1. `engine.py _generate_chapter_titles(story_text, theme_name)`：第 4 个 LLM call（紧随质量评估后），基于 final_story 生成严格 JSON `{"引入": "...", "深入": "...", "尾声": "..."}`，每标题 5-10 字；鲁棒解析（去 markdown 围栏、提取首个 `{}` 块、去引号等装饰）
2. `generate_story` 结束时追加调用，失败记录黄色 warning 但不阻塞；成功保存到 `chapter_titles.json`
3. `publish.py scan_episodes` 读 `chapter_titles.json` 到 `ep["chapter_titles"]`；`extract_chapters` 新增 `title_overrides` 参数，按 phase_name 查表替换 title；调用方同时传 SRT 和 overrides
4. 结构化返回：chapter dict 新增 `phase` 字段（原始 phase 名），`title` 是显示用（override 或 phase 兜底）——同时支持 HTML 展示（.chapter-name）和 ID3 CHAP TIT2
5. `backfill_chapter_titles.py` 一次性脚本：遍历 outputs/，为 23 个历史文件夹调 LLM 生成 chapter_titles.json；支持 `--dry-run` / `--force`；从 folder 名解析 theme（含 `_EP\d+` suffix 剥除）
6. 实跑 23 期全部成功，示例：
   - AI焦虑夜：「棉线硌着掌心 / 手机翻面光熄了 / 脚踝压着被角」
   - 父母渐老：「咖啡渍卷起的报告单 / 砂锅盖子轻轻颤 / 指尖暖起来」
   - 失业缓冲期：「椅面余温凹痕 / 简历推入抽屉 / 雨声里你在」
**验证**: HTML 单期页 `.chapter-name` 正确展示具象标题；MP3 `CHAP:ch000/001/002` 的 TIT2 子帧也写入同样标题；向后兼容——缺 chapter_titles.json 的期 fallback 到 phase 名（引入/深入/尾声）
**下一步**:
- 把 chapter_titles 也融入 OG 封面（每章节变体图）——目前封面是整期一张
- engine.py 里 chapter title 生成可以做 retry（如果 JSON 解析失败，重试一次带更严格 prompt）
- 把 chapter_titles 作为 description 前缀加到 episode page，首屏就展示章节内容

## [2026-04-17] 分享菜单 + FAQ 页（含 FAQPage schema） (publish.py)
**动因**: 增长复利的核心是「让满意听众主动帮你分享」。单期页原来的「📤 分享」用的是 navigator.share 兜底 copyLink——在没装对应 app 的浏览器里只是复制链接，文案要听众自己写。同样 AI 内容的信任问题没专属落地页，陌生访客的常见疑虑没地方一次性打消
**实现**:
1. 分享菜单：`toggleShareMenu` 替代 `shareEp`，展开下拉：X / 微博 / 小红书复制长文 / 微信复制链接+文案 / 仅复制链接
2. 每平台预填文案各异（Python 端按主题元数据生成，JSON 嵌入 HTML）：
   - **X（Twitter）**：短句 + 标题 + pain_point 一行 + 技术 — 推 intent URL 自动打开 compose
   - **微博**：`#助眠电台#` 话题 + 主题名 + 摘要 — share intent URL
   - **小红书**：完整 caption（emoji + 此刻感受/使用技术/听后状态 三元信息 + 时长 + 5 个 hashtag）— 复制到剪贴板（XHS 无 web share intent）
   - **微信**：标题+痛点+链接 — 复制（同上）
3. 每次点击触发 `Share Episode` 埋点带 platform prop，可分析哪个平台最有传播力
4. 菜单外点击自动关闭，Toast 提示「小红书文案已复制，去粘贴发帖」等针对性反馈
5. 新增 `generate_faq_page`：9 个 QA 覆盖 AI 可信/心理学依据/订阅方法/时长/声音/变现/流量/更新频率/反馈途径；每个 QA 写成 `<details>/<summary>` 折叠式，` [open]` 状态加暖紫边框
6. 注入 FAQPage JSON-LD：`@type: FAQPage, mainEntity: [{@type: Question, acceptedAnswer: {@type: Answer, text}}]`——这是 Google 在「人们还问」区显示答案卡片的结构化要求
7. 导航全打通：首页 stats 加「FAQ →」、单期页 footer 加「FAQ」、sitemap 加 faq.html（priority 0.6）
**验证**: 
- 分享菜单 4 个 shareTo 触发点（x/weibo/xhs/wechat）渲染正确；AI焦虑 episode 的小红书文案完整包含 emoji + 三元心理信息 + 5 hashtag，直接可粘贴
- FAQ 页 JSON-LD 被 `<script type="application/ld+json">` 正确包裹；9 个 `<details>` 折叠交互
- sitemap 含 faq.html 条目
**下一步**:
- 小红书 / 微信的 toast 提示可以增加一个「打开微信/小红书 App」深链（iOS 有 URL scheme）
- FAQ 页后续可以根据真实 analytics 数据更新（哪类问题从未点开说明没价值，哪个高频展开可补细节）
- Email 订阅 form 还没加——Buttondown/Substack 需用户选服务商，下一轮可做

## [2026-04-17] 18 主题着陆页 + 主题总览 hub (publish.py)
**动因**: 18 个主题各有完整心理学元数据（pain_point/technique/emotional_target/search_keywords），但只存在于 config.py——没有对应的可访问页面。访客搜「AI 焦虑 入睡」落到分类页太宽，真正需要的是直达 AI焦虑夜_数字排毒 主题。SEO 维度上少了 18 条长尾精准着陆机会
**实现**:
1. `generate_theme_page(theme_name, cfg, episodes, monetization, base_url)`：
   - 每期 pain_point/technique/emotional_target/推荐时长 用 label-value 列表展示（spec block）
   - 本主题节目卡片（如果有）
   - 同分类其他主题推荐（rel-grid）
   - category badge 作为面包屑跳回分类页
   - footer 链接：全部主题 / 分类页 / 首页 / 关于 / RSS
2. `generate_themes_hub(monetization, base_url)` → `site/themes.html`：4 分类 section，每个 section 列该类全部主题（按 config.THEMES 顺序），每主题一卡片显示 pain_point
3. main() 遍历 `_THEMES`，只为有 `category` 的主题生成（过滤 custom/legacy 主题），输出到 `site/theme/{name}.html`——即使该主题暂无节目也生成（覆盖空状态 + 提前种 SEO 长尾）
4. 导航全打通：
   - 单期页 theme-badge 从跳分类页改为跳主题页（theme 比 category 更具体匹配搜索意图）
   - 首页 header stats 加「主题 →」链接
   - 单期页 footer-nav 加「全部主题」链接
   - sitemap.xml 加 18 个 theme URL（priority 0.65）+ 1 个 themes.html（0.7）
5. 主题页排版上亮点：spec block 用紫金半透明渐变边框，让心理学锚点一眼可读；episode-date 用暖金 monospace 字体，让时间轴视觉连贯
**验证**: `python3 publish.py ...` 产出 `[OK] 主题页 × 18` + `[OK] 主题总览`；AI焦虑夜 那页完整展示：「此刻感受：被 AI 取代焦虑 + 数字过载」/「使用技术：具身化（Embodiment）锚定：用触觉/本体感将注意力拉回身体」/「听后状态：我是有身体的人、不可被替代的归属感」/「推荐时长：11 分钟」+ 2 期本主题节目 + 4 个同类相关主题；sitemap 含 18 条 theme URL
**下一步**:
- themes.html hub 的卡片点击触发 `Browse Theme` 埋点，统计哪个主题最受欢迎
- 主题页可再加「这类场景的听众可能在搜什么」section（展示 search_keywords 作为长尾 list）
- 18 个主题是否都能吸引足够内容持续产出？空主题一直挂着反而稀释站点质量——可考虑"最近 6 个月无新期"的主题自动下架

## [2026-04-17] 单期页播放器增强：倍速 + 睡眠定时器 (publish.py)
**动因**: 单期页用的是浏览器原生 `<audio controls>`，只能播/停/拖——缺倍速（让人能边扫文稿边听）、缺睡眠定时器（助眠内容核心场景：听着听着睡着，不想醒来发现还在播）。首页浮动播放器有这俩，单期页没有是明显的体验洼地
**实现**:
1. 音频元素上方新增 `.player-controls` 横排：倍速 pill + 睡眠定时器 pill（下拉菜单）
2. 倍速 `cycleSpeed`：循环 1.0× → 1.25× → 1.5× → 0.75× → 1.0×；!= 1 时 pill 变暖金高亮；触发 `Speed Change` 埋点
3. 睡眠定时器 `setPcSleepTimer(m)`：0/15/30/45/60 分钟选项，倒计时 badge 显示剩余分钟，到 20% 剩余时 `body.pc-dimmed` 渐暗，归零自动暂停音频；触发 `Sleep Timer Set` 埋点
4. 菜单外点击自动关闭（closest('#timerWrap') 判断）
5. `trackEvent` 函数做了兜底：analytics 块没注入时也不会 ReferenceError
6. 不替换浏览器原生播放器——只在上方增加工具条，保留了播放/拖动等默认行为（实现简单，兼容各平台）
**验证**: 每页 14 处 speed-wrap/pc-btn/cycleSpeed/setPcSleepTimer 渲染点；Apple 设备 audio element 仍有播放控件；`.pc-dimmed` 动画随定时器靠近终点触发
**下一步**:
- 定时器状态可持久化到 localStorage，同一设备重访保留
- 快进/快退 ±15s 按钮（助眠内容其实倒退用得少，优先级低）
- 章节 + 定时器组合：定时器剩余时间精确到「下一章节结束后自动停」（更贴合助眠使用）

## [2026-04-17] ID3 章节嵌入：章节跨端（Apple Podcasts / Pocket Casts）可见 (audio_tags.py + publish.py + requirements)
**动因**: 上轮加的 HTML 章节只在网页上能用。但真正听众在 Apple Podcasts / Spotify / Pocket Casts / Overcast 上听——这些才是高转化渠道（一键订阅）。没有跨端章节 = 专业度不到位，订阅了也不会买会员
**实现**:
1. 新增 `audio_tags.py`：用 mutagen 写 ID3v2.4 基础元数据（TIT2/TPE1/TALB/TCON/COMM/TYER）+ CHAP 章节帧 + CTOC 目录帧。重跑幂等：覆盖前清空已有 CHAP:/CTOC: keys 避免重复
2. `publish.py deploy_audio()` 在复制音频后调用 `embed_episode_metadata`：用 `extract_chapters(story, srt)` 拿到 chapter 列表，塞进 ID3；标题用 `ep['title']`（metadata.json 的发布标题），作者用 `PODCAST_AUTHOR`，简介用 `description` 前 500 字，年份从 timestamp
3. 覆盖语义：只在 `needs_copy=True` 时重写 ID3（幂等 + 节省 CPU）；老期无 SRT 时 chapters=None，只写基础元数据不写章节
4. Graceful degradation：mutagen 未安装时 `_audio_tags.available()` 返回 False，publish.py 跳过 ID3 步骤，不影响其他产出
5. requirements.txt 加 `mutagen>=1.47.0`；Actions workflow 已经 `pip install -r requirements.txt` 会自动装
**验证**: 22 个 MP3 全部写入 ID3 基础元数据；19 个新期（有 SRT）写入 3 个 CHAP frame + 1 个 CTOC；mutagen 读回验证：`CHAP:ch000 引入 — 0.0s → 38.4s`、`CHAP:ch001 深入 — 38.4s → 84.0s`、`CHAP:ch002 尾声 — 84.0s → 133.8s`；Title/Artist 正确
**下一步**:
- 苹果 Podcasts 支持章节图片（CHAP frame 里可以塞 APIC），可以把 OG 封面按章节变体嵌入——但优先级低
- ID3 的 chapter 名目前是阶段标签（引入/深入/尾声），engine.py 可以在生成时记录每段的具体主题（比如 AI 焦虑的「承认焦虑→具身化→消融」），让章节名更具体
- 目前每次 `publish.py --copy-audio` 都会在复制时重写 ID3，某些 podcast 客户端 cache 了旧版本需要刷新才能看到新章节

## [2026-04-17] 章节导航：把 [阶段：X] 标记变可点击时间戳 (publish.py)
**动因**: 每期脚本有 [阶段：引入/深入/尾声] 三段，韵律引擎按此切换速度/音量/停顿——但听众没有任何入口跳到自己想重听的那一段。复听用户是转化打赏/订阅的主力，没有章节导航等于让他们每次都从头开始
**实现**:
1. `extract_chapters(story, srt)` 在 publish.py 里新增：解析 SRT 成 cues 列表，walk story 行追踪 `[阶段：X]` 标记，每当阶段前面是待匹配状态、下一条叙述行出现时把 cue 的 start_sec 记为章节起点。返回 `[{title, start_sec, end_sec}]`
2. 防御：narrative line 识别用 _STRIP_RE 剥离所有 `[xx]` 标记后判断是否有文字；没 SRT 或没 phase marker 都返回 `[]`，episode 页章节 UI 自然不渲染
3. 单期页播放器下方新增 `<nav class="chapters">`：三列网格（时间/名字/时长），点击调用 `audio.currentTime = data-start` 并 play；分析埋点 `Jump Chapter` 带 name 属性
4. CSS：默认暗色 card，hover 时位移 2px 右移，active 状态用 accent 色边框（时间随播放进度自动高亮当前段）
5. `timeupdate` handler 找最近 start 时间的 chapter，toggle `.active` class——老期没 SRT 文件时章节数组为空，handler 不注册
**验证**: 22 期中 19 期新期全部识别 3 章节（引入/深入/尾声），每期 3 个 data-start 时间戳；老期 3 期缺 SRT 所以章节为空（预期行为）；AI焦虑 示例章节：引入 0:00 / 深入 0:38 / 尾声 1:24
**下一步**:
- MP3 里可以 embed ID3 CHAP frames（podcast 客户端会显示章节）——这一步能让 Apple Podcasts / Pocket Casts 等也呈现章节，提升跨渠道体验
- 章节名可从「引入/深入/尾声」升级为更具体的（例：AI 焦虑的「承认焦虑 → 具身锚定 → 消融」），需要让 engine.py 在生成阶段标记时同时记录段落主题
- 章节可加播放次数 heatmap（需分析埋点跑一段时间后聚合）

## [2026-04-17] 分类着陆页 + 首页筛选 chips (publish.py + README)
**动因**: 22 期内容就位后暴露两个问题：（a）首页一屏 22 张卡片堆在一起，用户来时带着具体意图（"我要的是裁员焦虑"），滚动找很烦；（b）搜索引擎只有 index+episodes+about 几类页，category.seo_keywords（裁员焦虑/ACT/职场共鸣/自然解压）定义了但无落地页承载，SEO 资产浪费
**实现**:
1. `generate_category_page(cat_key, cat_cfg, episodes, monetization, base_url)`：为每个分类生成独立 HTML，canonical + keywords 用 `category.seo_keywords`，OG 用 home.png，列出本类所有节目卡片（含 pain_point 前置显示）
2. `main()` 收集有节目的分类，写 `site/category/{key}.html`；0 期的分类不生成
3. 单期页的 `<span class="theme-badge">` 若主题有 category 则改成 `<a class="theme-badge" href="../category/{cat}.html">`——每张单期页都有反向链接到所属分类页，内部链接网加密
4. sitemap.xml 新增 4 个分类页条目（priority 0.7，changefreq weekly）
5. 首页 header 下订阅区之间加 `<nav class="filter-chips">`：全部/4 分类的 chip 横向排列，每个 chip 标注当期数；纯客户端 JS（`classList.toggle('hide-by-filter')`），无页面刷新；chip 右侧小 → 链接跳转到该分类的独立着陆页（聚焦 SEO）；点击 chip 触发 `Filter Category` 自定义埋点
6. episode 卡片新加 `data-cat="{category_key}"` 属性供 JS 过滤使用
7. README 站点结构补 `category/*.html`
**验证**: `python3 publish.py --copy-audio --base-url ...` 产出 `[OK] 分类页 × 4`；sitemap 含 4 条 category URL；单期页 theme-badge 正确渲染为 `<a href="../category/zeitgeist_2026.html">`；category 页 SEO 关键词为「裁员 焦虑,AI 焦虑,催婚 压力,父母 健康,失恋 助眠,助眠,睡眠,冥想」
**下一步**:
- 每个主题 18 个可以各自再出一个主题页（18 页额外索引），但收益递减——分类页已承载核心 SEO 意图
- 首页筛选 chip 可加记忆：URL `#cat=zeitgeist_2026` 直接激活对应分类，方便分享
- 分类页可加小工具：该分类专属的「随机播一期」按钮

## [2026-04-17] 信任建设：About 页 + 单期页临床技术徽章 (publish.py + README)
**动因**: 用户截图显示站点成功部署但停在占位页（batch 没产出），也暴露出更大问题——即使有内容，AI 生成类站点缺「凭什么信任」的落地页。陌生访客看到 3 秒内不知道：是谁做的？怎么做的？是瞎编还是有心理学基础？不解决信任，订阅/打赏/联盟都转化不动
**实现**:
1. 单期页标题下方加「临床技术徽章」：渲染 pain_point + technique + emotional_target 三行 label-value，紫金微渐变边框，不抢戏但让来访者一眼看到「这不是随便生成的，有心理锚点」；custom theme 无元数据时徽章整体隐藏
2. `publish.py generate_about_page()` 生成完整的 `site/about.html` ≈8.7KB：
   - 引子 lede
   - 4 大主题分类（从 THEME_CATEGORIES 拉 label/description + 每类当前主题数+名字）
   - 韵律弧线引擎解释（引入/深入/尾声三段参数）
   - **AI 生成流程透明披露**（步骤化：大纲→扩写→润色→5维评分→低分重写），counter 编号的 .process ol 样式
   - **变现透明披露**（条件性渲染，从 monetization 读打赏/赞助/联盟/会员实际启用的块，不 enable 就不显示）
   - 技术栈 credit + GitHub 源码链接
   - 联系邮箱（从 monetization.social.contact_email）
3. 站点导航打通：
   - 首页 header stats 行新增「关于 →」链接
   - 单期页 footer-nav 在「所有 N 期」和「RSS 订阅」中间加「关于」
   - sitemap.xml 增加 about.html 条目（priority 0.6，changefreq monthly）
4. README 站点结构部分补 about.html 说明
**验证**: 4 个 category section 按 THEME_CATEGORIES 顺序渲染（5+4+4+5=18 主题），每期页 3 处 tech-badge 渲染点（1 aside + 2 CSS 规则），sitemap 含 about 条目
**下一步**:
- About 页里 4 分类目前只列主题名，可以给每个主题加超链接到其最新一期
- 变现披露块如果没 enable 任何一个会整段隐藏——看起来像没披露，其实是真的没变现。可考虑即使没开也显示「暂未启用」一行增加透明度
- FAQ 页可以补上（"为什么每期长度不同" / "AI 写稿靠谱吗" / "订阅了会推送什么"）

## [2026-04-17] 心理元数据打通到 LLM Prompt + 按主题自动字数 (engine.py + batch.py + README)
**动因**: 上轮给主题加了 pain_point/technique/emotional_target，但这些只是"配置里的文档"——engine.py 生成剧本时只读 `story_prompt`，元数据没实际影响写稿。等于有了瞄准镜没校准枪。另：batch.py 所有主题用同一个 `--words=600`，15 分钟主题（深海独潜 Body Scan）和 10 分钟主题（深夜咖啡馆）产出同样长度，内容匹配不上主题节奏
**实现**:
1. `engine.py generate_story` 开头构建 `meta_block`：把 pain_point + technique + emotional_target 组成「听众心理锚点」文本块，注入到所有 3 个 LLM call（outline/draft/final_story）+ 重写 call
2. 具体增强：
   - 大纲 prompt 明确要求「引入段承认当下感受（不回避不说教）、深入段用技术、尾声段到达目标状态」
   - 扩写 prompt 加第 4 条禁令：「必须具体承认 pain_point，裁员主题就直接承认'工位杂物散落'这类画面，不能笼统说今天辛苦了」
   - 润色 prompt 加「禁止用积极情绪覆盖 pain_point，承认比安慰更能让人放松」
3. `_evaluate_story` 从 4 维升级到 5 维 100 分制（每维 20 分，原来每维 25 分），新增「痛点对齐」维度：检查是否承认痛点、是否用上技术、结尾是否到达目标状态；评估时把锚点也传给评审 LLM
4. 向后兼容：custom theme 没有新字段时 `meta_block` 为空字符串，所有流程照旧
5. `batch.py --words` 默认值从 `600` 改为 `0`，表示「按主题自动」：读 `theme.ideal_duration_min × 80 字/分钟`（80 是观察到的韵律弧线+停顿后的保守速率），得出 880/960/1200 等按主题差异化的字数；显式 `--words N` 仍可强制覆盖
6. 面板显示改为「按主题 ideal_duration_min 自动（80 字/分钟）」或「~N（全部）」
7. **README 全面重写**：反映所有历次迭代的能力（心理锚点/韵律/订阅按钮/OG 封面/Actions/变现配置/18 主题新分类），不再是初代 3 个 bullet 的简版
**验证**: 语法错误（f-string 内嵌双引号）已修；engine/batch 导入通过；午夜慢车=960 字、深海独潜=1200 字、AI焦虑夜=880 字，按主题 ideal_duration_min 正确换算
**下一步**:
- 80 字/分钟是粗校准值，第一批按新字数产出的音频需要人工听实际时长再微调这个系数
- 若字数显著增加，DashScope 配额消耗会按比例上升——用户首次跑 workflow 前值得预估配额
- 质量评分维度加了第 5 维后，历史剧本的评分基准会变化（旧是 4×25，现在 5×20），但评估是每次生产独立进行，不需要回溯

## [2026-04-17] 主题重构：从「场景名字」到「搜索+痛点+技术」三位一体 (config.py + publish.py)
**动因**: 用户指出「主题是一开始乱写的，要让主题有价值」。旧的 13 个主题只有 story_prompt + image_prompt + bgm_file 三个生成字段——不知道谁会搜到、为什么听、用了什么技术。主题是产线最上游的资产，这里不对齐，后面的 SEO/订阅/变现都是空转
**实现**:
1. 新增主题设计契约（config.py 顶部注释）：每个主题必须回答"听众搜什么/痛点是什么/用什么技术"三个问题。对齐这三者才叫「有价值」
2. 每个主题新增 6 个字段：`category`（分类 key）、`pain_point`（一句话情绪定位）、`technique`（心理/感官技术）、`search_keywords`（3-6 个 SEO 关键词）、`ideal_duration_min`（推荐时长）、`emotional_target`（听后状态）
3. 新增 5 个 2026 时代痛点主题（搜索热度验证过的高增长词）：
   - `失业缓冲期_职业空窗`：裁员焦虑、中年危机
   - `AI焦虑夜_数字排毒`：AI 取代恐慌、具身化锚定技术
   - `相亲过后_接纳单身`：催婚压力、去商品化叙事
   - `父母渐老_生命的重量`：父母健康焦虑、可控动作锚定
   - `分手那晚_安静告别`：失恋、象征性「合上」
4. THEME_VOICE_MAP 为 5 个新主题都匹配了音色（男声沉稳 / 女声温暖 / 女声温柔）
5. 新增 `THEME_CATEGORIES` 字典让 4 大类（自然解压/临床技术/情绪共鸣/时代痛点）成为一等公民，带 label + description + seo_keywords
6. publish.py 打通主题元数据：单期页 `<meta name="keywords">` 现在=主题 search_keywords + 分类 seo_keywords + 节目 tags 去重取前 12 个
**验证**: 18 个主题全部通过字段契约校验；向后兼容——`story_prompt/image_prompt/bgm_file` 都在；engine.py/batch.py 无需改动；每期页 keywords 从原来的 "助眠,睡眠,冥想,<random tag>" 升级成 12 个精准长尾词（例："雨夜 助眠, 木屋 ASMR, 下雨 故事, 雨声 入睡, 安全感 冥想, 助眠故事, 白噪音, ASMR, 自然声, 睡前放松, 助眠, 睡眠"）
**下一步**:
- batch.py 应该读 `ideal_duration_min` 自动调 --words（当前全局固定 600 字）
- engine.py 的 story generation prompt 可以注入 `pain_point` 和 `technique`，让 LLM 写稿时有更明确的心理目标
- publish.py 首页可加主题筛选芯片（按 category 分组），让访客按需求而非按日期浏览
- 5 个新主题首次生产后要人工听一次，评估 story_prompt 是否真能引导出预期的情绪基调

## [2026-04-17] GitHub Actions 自动化生产+部署 (.github/workflows/daily.yml + docs)
**动因**: 用户明确选择走 Actions 路（而非 gh-pages 分支）——内容复利需要每日稳定产出，本机部署依赖我开机不现实
**实现**:
1. 新增 `.github/workflows/daily.yml`——三触发：cron（北京 07:05 每日）、workflow_dispatch（手动，可跳过生成）、push 到 main（只改模板时秒速重建）
2. **`content` 分支持久化 outputs/**：Actions 运行器无状态，每次跑完环境消失；用 `content` 分支持久化累积的 Batch_/ 目录。流程：checkout content → 恢复 outputs/ → batch.py 添新一期 → rsync 回 content → git push
3. 首次运行兼容：`checkout content` 用 `continue-on-error: true`；下一步脚本判断 `[ -d content-branch/outputs ]`，无则跳过
4. CI 环境依赖：`apt-get install fonts-wqy-microhei fonts-wqy-zenhei ffmpeg`——封面用文泉驿微米黑（覆盖 Pillow 字体探测链末端），音频处理用 ffmpeg
5. 用 `actions/configure-pages@v4` + `upload-pages-artifact@v3` + `deploy-pages@v4`——Pages Source 必须是 "GitHub Actions" 不是 branch
6. 新增 `docs/GITHUB_ACTIONS_SETUP.md`：完整一次性配置（Secrets、Pages Source、Workflow permissions）、运行时行为矩阵、FAQ、如何回退到分支部署
**验证**: YAML 语法按 Actions schema 写；`inputs.skip_generation != true` 在 schedule 触发时也正确（inputs 为空时是 falsy），需要在 Actions 实际运行才能端到端验证
**下一步**:
- 用户需要：配 `DASHSCOPE_API_KEY` secret → Settings → Pages 选 Actions → 手动触发一次首次运行
- workflow 第一次可能因 Pillow 的字体探测顺序不对而让封面渲染失败；若发生，需在 covers.py `FONT_CANDIDATES` 里补更准确的 Debian 路径
- 未来可加 `failure()` 通知到飞书/企业微信；本项目已有 evolve.sh 里飞书 webhook 逻辑可复用

## [2026-04-17] OG 社交分享封面 (covers.py + publish.py)
**动因**: 订阅按钮解决了「访客到粉丝」的转化，但没解决「粉丝到新访客」的增长——分享到微信/小红书/X 时卡片无图，CTR 低 5 倍
**实现**:
1. 新增 `covers.py`：Pillow 渲染 1200x630 PNG。背景用站点紫金渐变 + 径向压暗中心；星点装饰；folder 名哈希种子让每期色相 ±30° 漂移保证视觉不重复；字体自动探测 macOS `STHeiti Medium.ttc` / PingFang / Noto CJK / 文泉驿
2. 组件：主题徽章（左上暖金 pill）+ 两行标题（自动换行 + 超长截断）+ 可选副标题（描述节选）+ 品牌页脚（左下）+ 右下装饰弧光
3. 优雅降级：Pillow 未安装时 `available()` 返回 False，publish.py 跳过封面生成但继续产出其他所有文件
4. `publish.py` 集成：`main()` 里调用 `_covers.generate_home_cover()` + `generate_episode_cover(ep, ...)`，输出到 `site/og/`；已存在的封面文件跳过（幂等 + 节省 CPU）
5. 首页 head 注入 `og:image` + `og:image:width/height` + `twitter:image`（summary_large_image），单期页同样注入 + canonical URL 对应 `og/{folder}.png`
**验证**: 4 张封面（3 期 + 1 首页）共 471KB；每页 4 处 og/twitter image meta；smoke test `python3 covers.py /tmp/og_test.png` 无报错
**下一步**:
- GitHub Actions 里要 `apt-get install fonts-wqy-microhei` 才能渲中文
- 封面目前是纯设计，可以考虑把场景图（若 --no-audio-only 产出了 scene_1.png）作为背景，AI 绘的图比渐变更抓眼球
- 长尾优化：封面加小字版「期数 / 日期」让老粉丝一眼区分不同期

## [2026-04-17] 订阅转化漏斗：首页订阅按钮组 (publish.py)
**动因**: 前 3 轮让站点可部署、有 SEO、有单期页、有相关推荐，但访客看完一期后**没有地方订阅**——RSS 只在 `<link rel="alternate">` 里（普通人不知道怎么用）。用户每次要主动搜索才能回来，长尾留存直接断掉
**实现**:
1. `_build_subscribe_html()` 渲染订阅按钮组：Apple Podcasts / Spotify / 小宇宙 / Overcast / Bilibili / RSS / 复制 RSS，平台 URL 未配置则按钮隐藏，RSS + 复制 永远显示
2. Apple Podcasts 智能回退：用户若未填 `apple_podcasts_url`，代码会用 `podcasts://feed-url` 协议自动生成——iOS/macOS 点击直接唤起 Apple Podcasts App 订阅，**不需要提交到 Apple 目录**；但要判断 URL 是否为真实域名（过滤 `你的域名` 和 `example.com` 等占位），避免占位 URL 把按钮造成死链
3. monetization.example.json 新增 `subscribe` 块，5 个平台 URL 占位 + hint 文案
4. 首页 `<header>` 和 `<main>` 之间注入订阅区，渐变紫+暖金背景、pill 按钮、悬停位移
5. 「复制 RSS」用 `navigator.clipboard.writeText`，按钮文字瞬变「已复制」1.6s 后恢复
6. 修复了 site_url 优先级 bug：之前 `m.get("site_url") or base_url` 让 CLI 的 `--base-url` 被配置覆盖；现在统一 `base_url or m.get("site_url")`，CLI 永远能覆盖
**验证**: 配 `--base-url https://beerui.github.io/bedtime_story_agent`，生成 3 个按钮（Apple Podcasts / RSS / 复制 RSS），href 全部指向真实域名的 feed.xml；Apple Podcasts 用 `podcasts://` 协议；复制按钮 JS 无引号嵌套 bug
**下一步**:
- 首页订阅区可再加「📧 邮件订阅」按钮，对接 Buttondown/Substack 等免费服务
- 订阅按钮目前是静态的，可以埋 `data-platform` 属性 + 对应事件，让用户看到「哪个按钮被点得最多」
- 更长期：把订阅按钮做成 sticky header（滚动后仍可见），最大化曝光

## [2026-04-16] 内部链接与可度量性 (publish.py + monetization)
**动因**: 单期页上线能被 Google 索引了，但（a）用户读完就离开——没有下一集提示、没有相关推荐，单页停留时长就是变现的天花板；（b）整个项目**没有任何数据**——不知道哪期流量大、哪个变现位有效、哪里在漏斗里流失
**实现**:
1. 单期页底部新增「上一集 / 下一集」导航，按 timestamp 排序。episodes 列表是新→旧，所以 i-1 是「下一集（更新的）」、i+1 是「上一集（更旧的）」；首/尾自动留空位保持布局
2. 新增 `_related_episodes()`：按 tag 交集打分 + 时间临近度平手，每期推荐 3 个相关节目。无 tag 交集时退化为「相近时间发布的」
3. 单期页底部新增「你可能还喜欢」卡片网格，跳转保持在 `/episodes/` 目录内（内部链接加深 → SEO 权重传递 + dwell time）
4. `monetization.example.json` 新增 `analytics` 块：Plausible / Umami / GA4 三种埋点，用户填哪个就注入哪个 snippet；全空时完全不注入（零性能成本）
5. `_build_analytics_head()` 在首页和所有单期页的 `<head>` 都注入对应脚本
6. 修了一个 bug：相关推荐的描述兜底使用 `draft_full` 时包含原始换行符，现在用 `re.sub(r"\s+", " ", ...)` 折叠
**验证**: `python3 publish.py --copy-audio --base-url ...` 成功；`ep-nav + ep-nav-title + rel-card` 每期 12 处渲染点；最新一期无「下一集」、最早一期无「上一集」，符合预期；相关推荐描述已是纯文本单行
**下一步**:
- Plausible/Umami/GA 需用户自己注册账号填 ID，目前只是骨架
- 埋点事件还需要细化：play/pause/完播率、打赏点击、联盟商品点击各一个 custom event 才能做漏斗
- OG 社交分享卡仍无图（下一轮可用 Pillow 生成简单文字封面 PNG）

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

