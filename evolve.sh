#!/usr/bin/env bash
# evolve.sh — 触发一次自我进化，完成后通知
#
# 用法:
#   ./evolve.sh              # 执行一轮进化
#   ./evolve.sh --dry-run    # 只分析不执行
#
# 定时执行:
#   crontab -e
#   0 22 * * * cd ~/Desktop/bedtime_story_agent && ./evolve.sh >> evolve.log 2>&1
#
# 通知配置 (.env):
#   EVOLVE_FEISHU_WEBHOOK=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
#   或
#   EVOLVE_WEBHOOK_URL=https://任意webhook地址

set -euo pipefail
cd "$(dirname "$0")"

# ---------------------------------------------------------------------------
# 加载 .env
# ---------------------------------------------------------------------------
if [[ -f .env ]]; then
    set -a
    source <(grep -v '^\s*#' .env | grep -v '^\s*$')
    set +a
fi

FEISHU_WEBHOOK="${EVOLVE_FEISHU_WEBHOOK:-}"
GENERIC_WEBHOOK="${EVOLVE_WEBHOOK_URL:-}"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# ---------------------------------------------------------------------------
# 通知函数
# ---------------------------------------------------------------------------
notify() {
    local title="$1"
    local body="$2"
    local status="$3"  # success / failure

    local icon="✅"
    [[ "$status" == "failure" ]] && icon="❌"

    # 1. 飞书 webhook
    if [[ -n "$FEISHU_WEBHOOK" ]]; then
        local card
        card=$(cat <<CARD
{
  "msg_type": "interactive",
  "card": {
    "header": {
      "title": {"tag": "plain_text", "content": "${icon} ${title}"},
      "template": "$( [[ "$status" == "success" ]] && echo "green" || echo "red" )"
    },
    "elements": [
      {"tag": "markdown", "content": "${body//\"/\\\"}"},
      {"tag": "note", "elements": [{"tag": "plain_text", "content": "🤖 bedtime_story_agent · ${TIMESTAMP}"}]}
    ]
  }
}
CARD
)
        curl -sS -X POST "$FEISHU_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "$card" > /dev/null 2>&1 || true
        echo "[notify] 飞书通知已发送"
    fi

    # 2. 通用 webhook (POST JSON)
    if [[ -n "$GENERIC_WEBHOOK" ]]; then
        curl -sS -X POST "$GENERIC_WEBHOOK" \
            -H "Content-Type: application/json" \
            -d "{\"title\":\"${icon} ${title}\",\"body\":\"${body//\"/\\\"}\",\"status\":\"${status}\",\"timestamp\":\"${TIMESTAMP}\"}" \
            > /dev/null 2>&1 || true
        echo "[notify] Webhook 通知已发送"
    fi

    # 3. macOS 桌面通知 (兜底)
    if command -v osascript &>/dev/null; then
        osascript -e "display notification \"${body:0:200}\" with title \"${icon} ${title}\"" 2>/dev/null || true
    fi
}

# ---------------------------------------------------------------------------
# 提取最新进化摘要
# ---------------------------------------------------------------------------
extract_latest_evolution() {
    # 读取 EVOLUTION_LOG.md 中最后一个 ## 块
    if [[ ! -f EVOLUTION_LOG.md ]]; then
        echo "（无进化日志）"
        return
    fi
    awk '/^## \[/{found=1; buf=$0; next} found && /^## \[/{exit} found{buf=buf"\n"$0} END{print buf}' EVOLUTION_LOG.md
}

# ---------------------------------------------------------------------------
# Agent prompts
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
EVOLUTION_HASH_BEFORE=$(git rev-parse HEAD 2>/dev/null || echo "none")

if [[ "${1:-}" == "--dry-run" ]]; then
    echo "[evolve] ${TIMESTAMP} 干跑模式——仅分析"
    claude -p "$DRY_RUN_PROMPT" --dangerously-skip-permissions
    exit 0
fi

echo "[evolve] ${TIMESTAMP} 启动进化"

# 运行 agent，捕获退出码
set +e
claude -p "$PROMPT" --dangerously-skip-permissions 2>&1 | tee /tmp/evolve_output.txt
EXIT_CODE=${PIPESTATUS[0]}
set -e

EVOLUTION_HASH_AFTER=$(git rev-parse HEAD 2>/dev/null || echo "none")

if [[ "$EVOLUTION_HASH_BEFORE" != "$EVOLUTION_HASH_AFTER" ]]; then
    # 有新提交——进化成功
    COMMIT_MSG=$(git log --oneline -1)
    SUMMARY=$(extract_latest_evolution)
    DIFF_STAT=$(git diff --stat "${EVOLUTION_HASH_BEFORE}..${EVOLUTION_HASH_AFTER}" 2>/dev/null | tail -1)

    notify "进化完成" "**${COMMIT_MSG}**\n\n${SUMMARY}\n\n\`${DIFF_STAT}\`" "success"
    echo "[evolve] ${TIMESTAMP} 进化完成: ${COMMIT_MSG}"
else
    # 无新提交
    if [[ $EXIT_CODE -ne 0 ]]; then
        LAST_LINES=$(tail -5 /tmp/evolve_output.txt 2>/dev/null | tr '\n' ' ')
        notify "进化失败" "Agent 退出码 ${EXIT_CODE}\n${LAST_LINES}" "failure"
        echo "[evolve] ${TIMESTAMP} 进化失败 (exit ${EXIT_CODE})"
    else
        notify "进化跳过" "Agent 分析后认为当前无需改进" "success"
        echo "[evolve] ${TIMESTAMP} 无变更"
    fi
fi

rm -f /tmp/evolve_output.txt
