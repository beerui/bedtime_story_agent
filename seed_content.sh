#!/usr/bin/env bash
# 把本地 outputs/ 推到 content 分支 —— 为 GitHub Actions 播种历史内容。
#
# 场景：
#   - 本地批量跑了 batch.py 产出多期内容，想让 Actions 下次运行时就有存量
#   - Actions 没开通前，先本地生产几期把站点填上
#   - 迁移账号或换仓库时保留内容历史
#
# 流程：
#   1. 临时工作目录 clone content 分支（不存在则 init）
#   2. rsync outputs/ → temp/outputs/
#   3. git commit + push 到 origin/content
#
# 与 deploy.sh 的区别：
#   deploy.sh 推 site/ 到 gh-pages（旧部署路径）
#   seed_content.sh 推 outputs/ 到 content（Actions 数据层）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
OUTPUTS_DIR="$ROOT/outputs"

if [ ! -d "$OUTPUTS_DIR" ] || [ -z "$(ls -A "$OUTPUTS_DIR" 2>/dev/null | grep -v '^\.')" ]; then
  echo "ERROR: outputs/ 为空，先 python3 batch.py --count N --audio-only"
  exit 1
fi

if ! git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: 未配置 git remote origin"
  exit 1
fi

ORIGIN_URL="$(git -C "$ROOT" remote get-url origin)"
EP_COUNT=$(ls "$OUTPUTS_DIR" | grep -c '^Batch_' || echo 0)
echo "==> 准备把 $EP_COUNT 期内容推到 content 分支"
echo "    origin: $ORIGIN_URL"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$TMP_DIR"

# 尝试 clone content 分支；失败则 init 空分支
if git clone -q --single-branch --branch content "$ORIGIN_URL" repo 2>/dev/null; then
  echo "==> 拉取现有 content 分支"
  cd repo
else
  echo "==> content 分支不存在，初始化"
  mkdir repo
  cd repo
  git init -q -b content
  git remote add origin "$ORIGIN_URL"
fi

# 覆写 outputs/（--delete 保证本地的删除也同步，避免旧垃圾）
mkdir -p outputs
rsync -a --delete "$OUTPUTS_DIR/" outputs/

git config user.name "$(git -C "$ROOT" config user.name || echo bedtime-seed)"
git config user.email "$(git -C "$ROOT" config user.email || echo seed@local)"

git add -A outputs
if git diff --cached --quiet; then
  echo "==> content 分支已是最新，无变化"
else
  git commit -q -m "seed: $EP_COUNT episodes at $(date +%Y-%m-%d-%H%M)"
  git push -q origin content
  echo "==> 已推送 $EP_COUNT 期到 origin/content"
fi

echo ""
echo "✓ 下一步：Actions 标签页 → Run workflow（选 skip_generation=true）"
echo "  就会用刚推送的内容直接部署，不消耗 DashScope 配额"
