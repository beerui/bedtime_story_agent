# Bedtime Story Agent

全自动助眠音频内容生产管线 + 可部署站点 —— 从文字到上线，一个命令搞定。

## 它能做什么

输入一个主题，自动完成：

1. **AI 写稿（含心理锚点）** — 三轮 LLM 生成（心理学大纲 → 口播稿 → 去 AI 腔润色），主题的 `pain_point/technique/emotional_target` 元数据直接注入 prompt，LLM 有明确心理目标；质量评估采用 5 维 100 分制（含「痛点对齐」维度），低分自动重写。
2. **韵律弧线配音** — 全局 speed/volume/pause 曲线，从正常语速渐进到极缓极轻，模拟真人催眠节奏。
3. **BGM 混音 + 双耳节拍（可选）** — AI 选曲 + Alpha→Theta→Delta 渐变双耳拍，输出可直接发布的成品 MP3。
4. **站点产出** — 每期独立 SEO 页（完整文稿 + OG 封面 + PodcastEpisode schema + 上/下集导航 + 相关推荐 + 章节跳转） + 首页订阅按钮组（Apple Podcasts / Spotify / 小宇宙 / RSS 等） + 分类着陆页 + sitemap/robots/404 + MP3 内嵌 ID3 章节（Apple Podcasts 等播客 App 跨端可见）。
5. **自动化部署** — GitHub Actions 每日 cron 生产一期 + 推 `content` 分支存音频 + 发布到 GitHub Pages。

```
outputs/Batch_20260417_xxxx_午夜慢车/
├── story_draft.txt      # 剧本（含韵律标记）
├── final_audio.mp3      # 成品音频（配音 + BGM）
├── subtitles.srt        # SRT 字幕
├── metadata.json        # 发布元数据
├── voice.mp3            # 纯配音
└── scene_1.png          # 场景图（非 --audio-only）

site/                    # 可直接部署到 GitHub Pages / Vercel / Netlify
├── index.html           # 首页（订阅按钮 + 分类筛选 + 节目列表 + 支持板块）
├── about.html           # 关于页（4 分类/生成流程/变现披露，信任建设）
├── category/*.html      # 4 个分类着陆页（按 SEO 意图独立打关键词）
├── episodes/*.html      # 每期独立长文页（SEO 长尾 + 心理技术徽章 + 章节导航 + 倍速+睡眠定时器）
├── audio/*.mp3          # 扁平化音频
├── og/*.png             # 1200x630 社交分享封面
├── feed.xml             # Podcast RSS 2.0
├── sitemap.xml          # 搜索引擎索引
└── robots.txt
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

只需要一个阿里云 DashScope API Key（[免费申请](https://dashscope.console.aliyun.com/)）：

```bash
echo "DASHSCOPE_API_KEY=sk-你的key" > .env
```

一个 key 覆盖：文本生成（Qwen）+ 语音合成（CosyVoice）+ 视频生成（Wan2.x）。CosyVoice 额度用完后自动降级为免费的 edge-tts。

### 3. 批量生产 + 本地预览

```bash
# 随机 3 个主题，纯音频模式（约 90 秒/期）
python3 batch.py --count 3 --audio-only

# 生成可部署站点（包含封面、RSS、sitemap、episode 页）
python3 publish.py --copy-audio --base-url https://你的域名.com

# 本地预览
cd site && python3 -m http.server 8888
```

### 4. 发布到 GitHub Pages（两种路径）

**A. 本机一键推（快速）** — `./deploy.sh https://你的用户名.github.io/仓库名` → 推送到 `gh-pages` 分支，Pages Source 选 branch。

**B. GitHub Actions 每日自动化（推荐）** — 详见 [docs/GITHUB_ACTIONS_SETUP.md](docs/GITHUB_ACTIONS_SETUP.md)。Settings 里配 `DASHSCOPE_API_KEY` secret → Pages Source 选 `GitHub Actions` → 手动触发一次首次运行；之后北京 07:05 每天自动产出一期并部署。

## 变现配置

复制 `monetization.example.json` 为 `monetization.json` 并填入真实链接，`publish.py` 会自动渲染 4 类变现入口：

- **打赏**（爱发电 / Buy Me a Coffee 等）
- **赞助位**（招商，邮件 mailto）
- **联盟商品网格**（蒸汽眼罩 / 白噪音机 / 降噪耳塞）
- **会员墙**（占位，未启用）
- **订阅按钮组**（Apple Podcasts / Spotify / 小宇宙 / Overcast / Bilibili，URL 未填则按钮不渲染）
- **分析埋点**（Plausible / Umami / GA4 三选一）— 首页和所有单期页都会自动注入所选脚本；播放/暂停/完成(80%)/复制 RSS 已自带 custom events

`monetization.json` 已加入 `.gitignore`，不会被推到 public repo。

## 18 个内置主题（4 大类）

| 分类 | 主题 | 痛点 / 技术 |
|------|------|-----------|
| **A. 自然场景解压** | 午夜慢车、雨夜山中小屋、深夜无人咖啡馆、篝火与星空、深海独潜 | 脑子停不下来 → 节律刺激 / 安全感包裹 / Body Scan |
| **B. 循证心理技术** | 溪流落叶_认知解离、极光冰屋_安全岛、阳光沙滩_自律训练、夏日午睡_怀旧退行 | ACT / Safe Place / Autogenic Training / Regression |
| **C. 情绪共鸣夜** | 末班地铁_卸下伪装、天台吹风_人际抽离、下班关机_反击上下级、深夜食堂_疯狂吐槽 | 职场疲惫 / 社交耗竭 / 反 PUA |
| **D. 时代痛点疗愈（2026）** | 失业缓冲期_职业空窗、AI焦虑夜_数字排毒、相亲过后_接纳单身、父母渐老_生命的重量、分手那晚_安静告别 | 裁员 / AI 替代恐慌 / 催婚 / 父母健康 / 失恋 |

每个主题都声明：`pain_point`（痛点）、`technique`（心理/感官技术）、`search_keywords`（SEO 关键词）、`ideal_duration_min`（推荐时长）、`emotional_target`（听后状态）。`batch.py` 默认按 `ideal_duration_min × 80 字/分钟` 自动调字数，无需 `--words`。

自定义主题：`python3 main.py` → 选择「告诉 AI 我的新想法」。

## 核心技术：韵律弧线引擎

普通 TTS 全篇匀速。本项目用 Prosody Curve 控制全局节奏：

```
引入段 (0-30%)   → speed=1.0  vol=1.0  句间停顿=0.3s
深入段 (30-70%)  → speed=0.82 vol=0.85 句间停顿=0.6s
尾声段 (70-100%) → speed=0.55 vol=0.3  句间停顿=2.0s
```

内联标记（`[慢速]`、`[轻声]`、`[极弱]`）是**乘法叠加**在曲线上，越到尾部效果越强。详见 `prosody.py`。

## 项目结构

```
config.py         # 配置中心（API、主题库 + 心理元数据、韵律曲线、TTS 规范）
engine.py         # 生产引擎（文本/语音/图像/视频/混音），prompt 注入 pain_point/technique
prosody.py        # 韵律弧线引擎
batch.py          # 批量生产 CLI（按主题 ideal_duration_min 自动调字数）
covers.py         # OG 社交分享封面生成（Pillow，1200x630）
audio_tags.py     # ID3 元数据 + CHAP 章节嵌入（mutagen，让 Apple Podcasts 等看到章节）
publish.py        # 站点生成（首页 + 单期页 + 分类页 + sitemap + RSS + 封面 + 订阅按钮 + 章节）
deploy.sh         # 一键推 gh-pages 分支
dedup.py          # 内容去重
main.py           # 交互式 CLI（完整视觉管线）
debug.py          # 模块级调试工具
binaural.py       # 双耳节拍生成器（Alpha→Theta→Delta）
.github/workflows/
  daily.yml       # 每日 cron 生产 + Pages 部署
docs/
  GITHUB_ACTIONS_SETUP.md  # Actions 一次性配置指南
monetization.example.json  # 变现配置样板（订阅链接/打赏/联盟/分析）
EVOLUTION_LOG.md  # 自治 agent 的历次改进记录
```

## 常用命令

```bash
# 生产 + 发布
python3 batch.py --count 3 --audio-only              # 生产 3 期
python3 publish.py --copy-audio                      # 生成站点
./deploy.sh https://user.github.io/repo              # 部署

# 测试
python3 -m unittest tests.test_cosyvoice_synthesize tests.test_prosody -v   # 28 个 mock 单测
RUN_COSYVOICE_LIVE=1 python3 -m unittest tests.test_cosyvoice_live -v       # 活调 CosyVoice

# 单期排查
python3 debug.py                                     # 模块级调试
python3 synthesize_once.py "要合成的文字"             # 独立 TTS
```

## License

MIT
