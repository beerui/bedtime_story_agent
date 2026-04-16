# Evolution Log

本项目由自治 agent 持续进化。每次改进记录在此，供后续 agent 感知历史、避免重复、持续迭代。

---

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

