#!/usr/bin/env bash
# 一键把 site/ 部署到 GitHub Pages 的 gh-pages 分支。
#
# 使用前提：
#   1. 项目已关联 GitHub remote（git remote add origin git@github.com:你/repo.git）
#   2. 仓库已开启 GitHub Pages，Source 选择「gh-pages branch / (root)」
#
# 用法：
#   ./deploy.sh                                          # 用相对路径（需本地预览）
#   ./deploy.sh https://你的用户名.github.io/repo        # 生成绝对 URL 的 RSS，更适合公开订阅
#
# 运行流程：
#   1. python3 publish.py --copy-audio --base-url $1 → 写满 site/
#   2. 新建孤儿分支 gh-pages，仅包含 site/ 的内容
#   3. 推送到 origin/gh-pages（--force，这个分支只存部署产物）
#   4. 切回你原来的工作分支

set -euo pipefail

BASE_URL="${1:-}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SITE_DIR="$ROOT/site"
CURRENT_BRANCH="$(git -C "$ROOT" rev-parse --abbrev-ref HEAD)"

echo "==> 生成站点（--copy-audio 自包含 ${BASE_URL:+· --base-url $BASE_URL}）"
if [ -n "$BASE_URL" ]; then
  python3 "$ROOT/publish.py" --copy-audio --base-url "$BASE_URL"
else
  python3 "$ROOT/publish.py" --copy-audio
fi

if [ ! -f "$SITE_DIR/index.html" ]; then
  echo "ERROR: site/index.html 未生成"; exit 1
fi

# GitHub Pages: 禁用 Jekyll（避免 _ 前缀被忽略），声明 CNAME（可选）
touch "$SITE_DIR/.nojekyll"

# 远端必须存在
if ! git -C "$ROOT" remote get-url origin >/dev/null 2>&1; then
  echo "ERROR: 尚未配置 git remote origin"; exit 1
fi

echo "==> 推送 site/ 到 gh-pages 分支"
TMP_DIR="$(mktemp -d)"
cp -R "$SITE_DIR/." "$TMP_DIR/"

cd "$TMP_DIR"
git init -q -b gh-pages
git add -A
git -c user.name="bedtime-deploy" -c user.email="deploy@local" \
    commit -q -m "deploy: $(date +%Y-%m-%d_%H:%M:%S)"
git remote add origin "$(git -C "$ROOT" remote get-url origin)"
git push -q --force origin gh-pages

echo "==> 清理"
cd "$ROOT"
rm -rf "$TMP_DIR"

echo ""
echo "✓ 已推送到 origin/gh-pages"
echo "  GitHub Pages 生效通常需要 1~2 分钟"
echo "  记得在 GitHub 仓库设置里把 Pages Source 指向 gh-pages 分支"
