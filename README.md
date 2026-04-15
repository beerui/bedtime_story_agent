# Bedtime Story Agent

全自动助眠音频内容生产管线 —— 从文字到可发布的成品，一个命令搞定。

## 它能做什么

输入一个主题，自动完成：

1. **AI 写稿** — 三轮 LLM 生成（心理学大纲 → 口播稿 → 去 AI 腔润色），内置质量评分和低分自动重写
2. **韵律弧线配音** — 全局 speed/volume/pause 曲线，从正常语速渐进到极缓极轻，模拟真人催眠节奏
3. **BGM 混音** — AI 选曲 + 自动混音，输出可直接发布的成品 MP3
4. **发布就绪** — 自动生成 SRT 字幕、多平台元数据（标题/简介/标签）、内容去重检测

```
outputs/Batch_20260415_午夜慢车/
├── story_draft.txt      # 剧本（含韵律标记）
├── final_audio.mp3      # 成品音频（配音 + BGM）
├── subtitles.srt        # SRT 字幕
├── metadata.json        # 发布元数据
├── voice.mp3            # 纯配音
└── scene_1.png          # 场景图（可选）
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

一个 key 覆盖：文本生成（Qwen）+ 语音合成（CosyVoice）+ 视频生成（Wan2.x）。

CosyVoice 额度用完后自动降级为免费的 edge-tts（微软语音），不影响生产。

### 3. 批量生产

```bash
# 随机 3 个主题，纯音频模式（约 90 秒/期）
python3 batch.py --count 3 --audio-only

# 指定主题
python3 batch.py --themes 午夜慢车 雨夜山中小屋 --words 800

# 全部 13 个主题一次性出完
python3 batch.py --all --audio-only
```

## 内置主题库（13 个）

| 分类 | 主题 |
|------|------|
| 自然场景 | 午夜慢车、雨夜山中小屋、深夜无人咖啡馆、篝火与星空、深海独潜 |
| 心理疗愈 | 溪流落叶_认知解离、极光冰屋_安全岛、阳光沙滩_自律训练、夏日午睡_怀旧退行 |
| 职场治愈 | 末班地铁_卸下伪装、天台吹风_人际抽离、下班关机_反击上下级、深夜食堂_疯狂吐槽 |

也支持自定义主题：`python3 main.py` → 选择「告诉 AI 我的新想法」。

## 核心技术：韵律弧线引擎

普通 TTS 全篇匀速。本项目用 Prosody Curve 控制全局节奏：

```
引入段 (0-30%)   → speed=1.0  vol=1.0  句间停顿=0.3s
深入段 (30-70%)  → speed=0.82 vol=0.85 句间停顿=0.6s
尾声段 (70-100%) → speed=0.55 vol=0.3  句间停顿=2.0s
```

内联标记（`[慢速]`、`[轻声]`、`[极弱]`）是**乘法叠加**在曲线上，越到尾部效果越强。

## 项目结构

```
config.py       # 配置中心（API、主题库、韵律曲线）
engine.py       # 生产引擎（文本/语音/图像/视频/混音）
prosody.py      # 韵律弧线引擎
batch.py        # 批量生产 CLI
dedup.py        # 内容去重
main.py         # 交互式 CLI（完整视觉管线）
debug.py        # 模块级调试工具
```

## License

MIT
