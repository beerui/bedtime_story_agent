#!/usr/bin/env python3
"""启动前诊断：一条命令告诉你"现在卡在哪、下一步去哪点"。

read-only 检查：不会自动执行破坏性操作。绿灯=已就绪，黄灯=可选但建议，红灯=必须处理才能继续。

用法:
    python3 launch.py           # 完整诊断 + 下一步引导
    python3 launch.py --quiet   # 只打总结 + 最下一步
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
GREEN = "🟢"
YELLOW = "🟡"
RED = "🔴"
DIM_START = "\033[2m" if sys.stdout.isatty() else ""
DIM_END = "\033[0m" if sys.stdout.isatty() else ""
BOLD = "\033[1m" if sys.stdout.isatty() else ""
BOLD_END = "\033[0m" if sys.stdout.isatty() else ""


class Check:
    __slots__ = ("status", "title", "detail", "next_step")

    def __init__(self, status: str, title: str, detail: str = "", next_step: str = ""):
        self.status = status  # 🟢 / 🟡 / 🔴
        self.title = title
        self.detail = detail
        self.next_step = next_step

    def is_blocker(self) -> bool:
        return self.status == RED


def _gh_available() -> bool:
    return shutil.which("gh") is not None


def check_git_remote() -> Check:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return Check(RED, "Git remote", "未配置 origin",
                         next_step="git remote add origin git@github.com:你/仓库.git")
        url = r.stdout.strip()
        if "github.com" not in url:
            return Check(YELLOW, "Git remote", f"origin 不是 GitHub: {url}",
                         next_step="确认 remote 是 GitHub（Actions/Pages 依赖 GitHub）")
        return Check(GREEN, "Git remote", url)
    except Exception as e:
        return Check(RED, "Git remote", f"检查失败: {e}")


def check_env_file() -> Check:
    env = ROOT / ".env"
    if not env.is_file():
        return Check(YELLOW, ".env", "不存在（本地生产时需要）",
                     next_step='echo "DASHSCOPE_API_KEY=sk-你的key" > .env')
    text = env.read_text(encoding="utf-8")
    if "DASHSCOPE_API_KEY=" not in text:
        return Check(RED, ".env", "缺 DASHSCOPE_API_KEY",
                     next_step='加一行: DASHSCOPE_API_KEY=sk-你的key')
    for line in text.splitlines():
        if line.strip().startswith("DASHSCOPE_API_KEY="):
            value = line.split("=", 1)[1].strip().strip('"\'')
            if not value or value.startswith("sk-你"):
                return Check(RED, ".env",
                             "DASHSCOPE_API_KEY 为空或占位",
                             next_step="填真实 key（https://dashscope.console.aliyun.com/）")
            return Check(GREEN, ".env", f"DASHSCOPE_API_KEY 已设（{value[:4]}...{value[-4:]})")
    return Check(RED, ".env", "DASHSCOPE_API_KEY 未设")


def check_monetization() -> Check:
    mon = ROOT / "monetization.json"
    if not mon.is_file():
        return Check(YELLOW, "monetization.json", "未创建（变现 URL 会用占位）",
                     next_step="cp monetization.example.json monetization.json 并编辑")
    try:
        data = json.loads(mon.read_text(encoding="utf-8"))
    except Exception as e:
        return Check(RED, "monetization.json", f"JSON 解析失败: {e}")
    email = ((data.get("social") or {}).get("contact_email") or "").strip()
    site = (data.get("site_url") or "").strip()
    issues: list[str] = []
    if not email or "你的域名" in email or ".local" in email:
        issues.append(f"social.contact_email={email or '空'} 还是占位")
    if not site or "你的域名" in site:
        issues.append(f"site_url={site or '空'} 还是占位")
    if issues:
        return Check(YELLOW, "monetization.json", "；".join(issues),
                     next_step="填真实邮箱和站点 URL（Apple Podcasts 提交时会校验）")
    return Check(GREEN, "monetization.json", f"contact={email} site={site}")


def check_outputs() -> Check:
    outputs = ROOT / "outputs"
    if not outputs.is_dir():
        return Check(YELLOW, "outputs/", "目录不存在——还没生产任何节目",
                     next_step="python3 batch.py --count 1 --audio-only")
    n = len([p for p in outputs.iterdir()
             if p.is_dir() and p.name.startswith("Batch_")])
    if n == 0:
        return Check(YELLOW, "outputs/", "没有 Batch_ 文件夹",
                     next_step="python3 batch.py --count 1 --audio-only")
    return Check(GREEN, "outputs/", f"{n} 个期数已生产")


def check_content_branch() -> Check:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "ls-remote", "--heads", "origin", "content"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return Check(YELLOW, "content 分支", "无法查询 remote（网络或无权限）",
                         next_step="./seed_content.sh 推送本地 outputs/")
        if not r.stdout.strip():
            return Check(YELLOW, "content 分支", "远端未创建",
                         next_step="跑 ./seed_content.sh 把 outputs/ 推到 content 分支")
        return Check(GREEN, "content 分支", "已存在于 origin/content")
    except Exception as e:
        return Check(YELLOW, "content 分支", f"检查跳过: {e}")


def check_site() -> Check:
    site = ROOT / "site"
    if not site.is_dir():
        return Check(YELLOW, "site/", "目录不存在",
                     next_step="python3 publish.py --copy-audio 生成站点")
    essentials = ["index.html", "feed.xml", "sitemap.xml"]
    missing = [e for e in essentials if not (site / e).is_file()]
    if missing:
        return Check(YELLOW, "site/", f"缺: {', '.join(missing)}",
                     next_step="python3 publish.py --copy-audio 重新生成")
    return Check(GREEN, "site/", f"index.html / feed.xml / sitemap.xml 齐全")


def check_gh_cli() -> Check:
    if not _gh_available():
        return Check(YELLOW, "gh CLI", "未安装（可选，装了能自动检查 Secrets/Pages）",
                     next_step="brew install gh && gh auth login（可跳过）")
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            return Check(YELLOW, "gh CLI", "已装但未登录",
                         next_step="gh auth login")
        return Check(GREEN, "gh CLI", "已装并登录")
    except Exception as e:
        return Check(YELLOW, "gh CLI", f"检查失败: {e}")


def _gh_repo_owner_name() -> tuple[str, str] | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(ROOT), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5,
        )
        url = r.stdout.strip()
        import re
        m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", url)
        if m:
            return m.group(1), m.group(2)
    except Exception:
        pass
    return None


def check_secret_dashscope() -> Check:
    if not _gh_available():
        return Check(YELLOW, "Secret: DASHSCOPE_API_KEY", "需要 gh CLI 才能验证",
                     next_step="去仓库 Settings → Secrets → Actions 确认")
    owner_name = _gh_repo_owner_name()
    if not owner_name:
        return Check(YELLOW, "Secret: DASHSCOPE_API_KEY", "无法解析仓库")
    owner, name = owner_name
    try:
        r = subprocess.run(
            ["gh", "secret", "list", "-R", f"{owner}/{name}"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return Check(YELLOW, "Secret: DASHSCOPE_API_KEY", "查询失败（可能权限不够）")
        if "DASHSCOPE_API_KEY" in r.stdout:
            return Check(GREEN, "Secret: DASHSCOPE_API_KEY", "已在 GitHub Secrets")
        return Check(RED, "Secret: DASHSCOPE_API_KEY", "未在仓库 Secrets 里",
                     next_step=f"gh secret set DASHSCOPE_API_KEY -R {owner}/{name}  或 "
                              f"去 https://github.com/{owner}/{name}/settings/secrets/actions 添加")
    except Exception as e:
        return Check(YELLOW, "Secret: DASHSCOPE_API_KEY", f"跳过: {e}")


def check_pages() -> Check:
    if not _gh_available():
        return Check(YELLOW, "GitHub Pages", "gh CLI 未装——无法验证",
                     next_step="仓库 Settings → Pages → Source: GitHub Actions")
    owner_name = _gh_repo_owner_name()
    if not owner_name:
        return Check(YELLOW, "GitHub Pages", "无法解析仓库")
    owner, name = owner_name
    try:
        r = subprocess.run(
            ["gh", "api", f"repos/{owner}/{name}/pages"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0:
            return Check(RED, "GitHub Pages", "未开启",
                         next_step=f"Settings → Pages → Source: GitHub Actions "
                                  f"(https://github.com/{owner}/{name}/settings/pages)")
        try:
            data = json.loads(r.stdout)
            source_type = (data.get("build_type") or "").lower()
            if source_type != "workflow":
                return Check(YELLOW, "GitHub Pages",
                             f"Source={source_type}，需要 'workflow' (GitHub Actions)",
                             next_step="Settings → Pages → Source: GitHub Actions")
            return Check(GREEN, "GitHub Pages",
                         f"已开启（{data.get('html_url', '')}）")
        except Exception:
            return Check(GREEN, "GitHub Pages", "已开启")
    except Exception as e:
        return Check(YELLOW, "GitHub Pages", f"跳过: {e}")


def check_workflow_status() -> Check:
    if not _gh_available():
        return Check(YELLOW, "Actions 状态", "需要 gh CLI")
    owner_name = _gh_repo_owner_name()
    if not owner_name:
        return Check(YELLOW, "Actions 状态", "无法解析仓库")
    owner, name = owner_name
    try:
        r = subprocess.run(
            ["gh", "run", "list", "-R", f"{owner}/{name}", "-L", "3",
             "--json", "status,conclusion,displayTitle,createdAt"],
            capture_output=True, text=True, timeout=10,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return Check(YELLOW, "Actions 状态", "还没有任何运行",
                         next_step=f"Actions 标签 → Daily episode + deploy → Run workflow "
                                  f"(https://github.com/{owner}/{name}/actions)")
        runs = json.loads(r.stdout)
        if not runs:
            return Check(YELLOW, "Actions 状态", "还没有任何运行")
        latest = runs[0]
        status = latest.get("status", "?")
        conclusion = latest.get("conclusion") or "in_progress"
        title = latest.get("displayTitle", "")[:40]
        if conclusion == "success":
            return Check(GREEN, "Actions 状态", f"最新运行成功: {title}")
        if conclusion in ("failure", "cancelled"):
            return Check(RED, "Actions 状态", f"{conclusion}: {title}",
                         next_step=f"点 https://github.com/{owner}/{name}/actions 看失败详情")
        return Check(YELLOW, "Actions 状态", f"{status}: {title}")
    except Exception as e:
        return Check(YELLOW, "Actions 状态", f"跳过: {e}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true", help="只打总结")
    args = parser.parse_args()

    checks = [
        check_git_remote(),
        check_env_file(),
        check_monetization(),
        check_outputs(),
        check_site(),
        check_content_branch(),
        check_gh_cli(),
        check_secret_dashscope(),
        check_pages(),
        check_workflow_status(),
    ]

    if not args.quiet:
        print()
        print(f"{BOLD}🌙 助眠电台启动诊断{BOLD_END}")
        print()
        for c in checks:
            print(f"  {c.status}  {c.title}")
            if c.detail:
                print(f"     {DIM_START}{c.detail}{DIM_END}")
            if c.next_step:
                print(f"     👉 {c.next_step}")
        print()

    blockers = [c for c in checks if c.is_blocker()]
    warnings = [c for c in checks if c.status == YELLOW]

    if blockers:
        first = blockers[0]
        print(f"{BOLD}⛔ 下一步（必须）：{BOLD_END}{first.next_step or first.title}")
    elif warnings:
        first = next((c for c in warnings if c.next_step), None)
        if first:
            print(f"{BOLD}🔶 下一步（建议）：{BOLD_END}{first.next_step}")
        else:
            print(f"{BOLD}🟢 所有必需项就绪——可以直接触发 Actions workflow{BOLD_END}")
    else:
        print(f"{BOLD}✅ 所有检查通过——站点应已上线{BOLD_END}")

    return 1 if blockers else 0


if __name__ == "__main__":
    sys.exit(main())
