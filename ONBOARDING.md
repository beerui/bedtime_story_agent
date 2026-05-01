# Welcome to BeerUI

## How We Use Claude

Based on 刘勇杰's usage over the last 30 days:

Work Type Breakdown:
  Improve Quality       ████████████░░░░░░░░  40%
  Build Feature         ███████░░░░░░░░░░░░░  25%
  Debug Fix             ███░░░░░░░░░░░░░░░░░  10%
  Other / Unclear       ████████░░░░░░░░░░░░  25%

Top Skills & Commands:
  /loop                 ██████████████████░░  51x/month
  /model                ██████████░░░░░░░░░░  28x/month
  /effort               █░░░░░░░░░░░░░░░░░░░  2x/month
  /superpowers:brainstorming  █░░░░░░░░░░░░░░░░░░░  1x/month

Top MCP Servers:
  _(none configured)_

## Your Setup Checklist

### Codebases
- [ ] bedtime_story_agent — https://github.com/beerui/bedtime_story_agent
  睡前故事/冥想音频自动化生产线：AI 写稿、TTS 配音、BGM 混音、多平台发布。

### MCP Servers to Activate
_(当前未配置 MCP 服务器。如需集成外部服务（如数据库、API），可在 `.claude/settings.json` 中添加。)_

### Skills to Know About
- [/loop](https://docs.anthropic.com/en/docs/claude-code/skills) — 定时循环执行任务。团队常用：`/loop 20m` 定期运行批量生产，持续改进项目质量并生成内容。
- [/model](https://docs.anthropic.com/en/docs/claude-code/models) — 切换 Claude 模型（Opus / Sonnet / Haiku），根据任务复杂度选择合适的模型。
- [/effort](https://docs.anthropic.com/en/docs/claude-code/effort) — 调整推理深度，简单任务可降低以加快响应。
- [/superpowers:brainstorming](https://docs.anthropic.com/en/docs/claude-code/skills) — 在实现功能前进行创意探索和需求分析，适合新功能规划阶段。

## Team Tips

_TODO — 团队协作经验待补充_

## Get Started

_TODO — 入门任务待补充_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
