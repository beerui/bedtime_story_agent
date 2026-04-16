#!/usr/bin/env bash
# evolve.sh — 触发一次自我进化
#
# 用法:
#   ./evolve.sh              # 执行一轮进化
#   ./evolve.sh --dry-run    # 只分析不执行（查看 agent 会做什么）
#
# 定时执行:
#   crontab -e
#   0 22 * * * cd ~/Desktop/bedtime_story_agent && ./evolve.sh >> evolve.log 2>&1

set -euo pipefail
cd "$(dirname "$0")"

PROMPT=$(cat <<'PROMPT'
你是这个项目的自治进化 agent。

请严格按照 evolve.md 中的思维框架执行：
1. 感知现状（读 CLAUDE.md、EVOLUTION_LOG.md、扫描代码）
2. 识别最高杠杆改进点
3. 实现、测试、提交、推送
4. 将本次进化记录追加到 EVOLUTION_LOG.md

只做 1 个改进，做到位。完成后停止。
PROMPT
)

DRY_RUN_PROMPT=$(cat <<'PROMPT'
你是这个项目的自治进化 agent。

请严格按照 evolve.md 中的思维框架执行前两步：
1. 感知现状（读 CLAUDE.md、EVOLUTION_LOG.md、扫描代码）
2. 识别最高杠杆改进点

只分析和报告，不要修改任何文件。告诉我你会做什么改进以及为什么。
PROMPT
)

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "[evolve] $(date '+%Y-%m-%d %H:%M:%S') 干跑模式——仅分析"
    exec claude -p "$DRY_RUN_PROMPT" --dangerously-skip-permissions
else
    echo "[evolve] $(date '+%Y-%m-%d %H:%M:%S') 启动进化"
    exec claude -p "$PROMPT" --dangerously-skip-permissions
fi
