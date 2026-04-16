# GitHub Actions 自动化部署配置

这个项目的 `.github/workflows/daily.yml` 可以每天自动生产一期新节目并部署到 GitHub Pages——你不需要本机开机。

## 一次性配置

### 1. 仓库 Settings → Secrets and variables → Actions

添加一个 Secret：

| Name | Value |
|------|-------|
| `DASHSCOPE_API_KEY` | 你的阿里云 DashScope API Key |

不需要手动加 `GITHUB_TOKEN`——Actions 会自动注入。

### 2. 仓库 Settings → Pages

- **Source** 选择 **`GitHub Actions`**（**不要**选 branch）
- 无需选分支或目录

### 3. 仓库 Settings → Actions → General

- **Workflow permissions** → **Read and write permissions**（让 Actions 能推 content 分支）
- 勾上 **Allow GitHub Actions to create and approve pull requests**

### 4. 首次触发

去 Actions 标签页 → 左侧选 **Daily episode + deploy to Pages** → 右上 **Run workflow** → **Run workflow**（用默认参数）。

首次运行会：
1. 因为 `content` 分支不存在而跳过「恢复 outputs/」（正常，continue-on-error 已处理）
2. 生成 1 期新节目
3. 创建 `content` 分支并推入 `outputs/`
4. 产出 site/ 并部署到 Pages

部署成功后，访问 `https://<你的用户名>.github.io/<仓库名>/` 能看到站点。

## 运行时行为

| 触发方式 | 动作 |
|---------|------|
| 每天 07:05 北京时间（cron） | 生产 1 期 → 持久化到 content → 部署 |
| 手动 workflow_dispatch | 可选跳过生成（只重建站点） + 可设期数 |
| Push 到 main（改 publish.py / covers.py / config.py / monetization.json / workflow 本身） | **只重建站点**，不生成新内容，秒级上线模板改动 |

## 为什么有两个分支

| 分支 | 内容 | 为什么 |
|------|------|--------|
| `main` | 源码（publish.py, covers.py, config.py 等） | 正常 git 仓库 |
| `content` | 产出（outputs/Batch_.../） | Actions 运行器无状态，每次跑完环境就没了；content 分支持久化积累的节目文件 |

你不需要直接操作 `content` 分支——Actions 自动维护。

## 手动触发的场景

- **`skip_generation = true`**：改了 `publish.py` 或 `monetization.json` 想立刻预览，但不想消耗 DashScope 配额
- **`count = 3`**：想一次补 3 期（比如断更几天后补齐）

## 本地 vs Actions 生产的配额

Actions 生产消耗 GitHub 免费 CI 时长（public repo 无限，private 每月 2000 分钟）+ DashScope 配额（文本 Qwen、语音 CosyVoice 共用同一 key 的配额）。

单期典型消耗：
- Qwen 文本：3 轮 LLM call，约 4K tokens
- CosyVoice：~800 字 TTS → 约 1 分钟音频生成（配额用 edge-tts 兜底自动降级）
- CI 时长：~4 分钟

## 常见问题

**Q: 首次运行失败：Permission denied pushing to content**
A: Settings → Actions → General → Workflow permissions 改成 **Read and write permissions**。

**Q: 部署成功但页面 404**
A: 第一次部署后 DNS/CDN 预热要 1~3 分钟，刷新即可。

**Q: 如何停止每日自动产出但保留手动触发**
A: 编辑 `.github/workflows/daily.yml`，注释掉 `schedule:` 块即可。

**Q: 想改每日触发时间**
A: 改 `cron: '5 23 * * *'` 里的数字。`23 5` 是 UTC 时间——北京 = UTC+8，所以北京 07:05 对应 UTC 23:05（前一天）。`0 16 * * *` = 北京 00:00。

## 调试 workflow 失败

1. Actions 标签页 → 点失败的那次运行
2. 展开红色的 step 看日志
3. 常见失败：
   - `DASHSCOPE_API_KEY` 未配或值错：第 `Produce new episode` step 报 401
   - 没装字体：`covers.py` 报 `Image.FreeTypeFont` 找不到——workflow 已 `apt-get install fonts-wqy-microhei` 兜底
   - content 分支推不上：看 Workflow permissions 设置

## 关闭自动化回到手动部署

想把自动化整个关掉：
- 删掉 `.github/workflows/daily.yml`
- 改回 `./deploy.sh` 本地部署流程
- Settings → Pages → Source 改回 `Deploy from a branch` → `gh-pages`
