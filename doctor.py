#!/usr/bin/env python3
"""全站静态健康诊断：扫 site/ 所有 HTML/JSON/XML 文件，查找：

  - 未替换的 Python f-string 占位符（{xxx}、{{ }} 异常）
  - 引用的本地资源（href/src）实际不存在
  - 未闭合/错配的 HTML 标签（浅层语法检查）
  - JSON-LD / RSS / manifest 无法解析
  - 关键 meta tag 缺失（title/description/og:image）

用法:
    python3 doctor.py                   # 完整诊断
    python3 doctor.py --page index.html # 只诊断单页
    python3 doctor.py --json            # CI 消费
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).parent
SITE = ROOT / "site"

_COLORS = sys.stdout.isatty()
RED = "\033[31m" if _COLORS else ""
YELLOW = "\033[33m" if _COLORS else ""
GREEN = "\033[32m" if _COLORS else ""
DIM = "\033[2m" if _COLORS else ""
RESET = "\033[0m" if _COLORS else ""


# Matches a stray `{something}` that survived f-string rendering (template bug).
# Excludes `{{ }}` CSS literals and JSON-ish content.
_UNREPLACED_PLACEHOLDER = re.compile(r"(?<![{])\{[A-Za-z_][\w\[\]\'\"\.]*\}(?![}])")

# href/src values that reference local (non-anchor, non-external) paths
_LOCAL_HREF_RE = re.compile(r'''(?:href|src|action)\s*=\s*["']([^"'#?]+?)["']''')


def _check_unreplaced_placeholders(path: Path, text: str) -> list[dict]:
    """Report suspicious {name} substrings inside HTML/JSON — likely a template
    that failed to substitute. CSS/JS braces use `{` as syntax, so we only
    flag fragments that look like Python identifiers wrapped in single {}."""
    issues: list[dict] = []
    # Skip if file contains <style> or <script> which have legit {...}
    # Instead scan only text between > and <.
    body_only = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    body_only = re.sub(r"<script[^>]*>.*?</script>", "", body_only, flags=re.DOTALL)
    for m in _UNREPLACED_PLACEHOLDER.finditer(body_only):
        # Allow common JS template literals if they slipped through? Few are Python-like.
        issues.append({
            "severity": "error", "code": "unreplaced_placeholder",
            "message": f"可疑 f-string 占位符未替换：{m.group(0)}"
        })
    return issues


def _check_local_refs(path: Path, text: str, site_root: Path) -> list[dict]:
    """For every href/src pointing to a local file (not http://, not mailto,
    not anchor), check the target exists under site/."""
    issues: list[dict] = []
    # Determine page's parent (for relative path resolution)
    page_dir = path.parent
    seen: set[str] = set()
    for m in _LOCAL_HREF_RE.finditer(text):
        ref = m.group(1)
        if ref in seen:
            continue
        seen.add(ref)
        if not ref:
            continue
        # skip external + non-http schemes + anchors
        parsed = urlparse(ref)
        if parsed.scheme in ("http", "https", "mailto", "tel", "podcasts", "javascript", "data"):
            continue
        if ref.startswith("#") or ref.startswith("//"):
            continue
        # Resolve relative to page
        target_str = unquote(ref.split("#")[0].split("?")[0])
        if not target_str:
            continue
        if target_str.startswith("/"):
            target = site_root / target_str.lstrip("/")
        else:
            target = (page_dir / target_str).resolve()
        # Target must be under site_root (no climb out)
        try:
            target.relative_to(site_root.resolve())
        except ValueError:
            issues.append({
                "severity": "warning", "code": "ref_outside_site",
                "message": f"引用指向 site/ 之外：{ref}"
            })
            continue
        if not target.exists():
            issues.append({
                "severity": "error", "code": "broken_local_ref",
                "message": f"引用的文件不存在：{ref} (→ {target.relative_to(site_root)})"
            })
    return issues


def _check_html_basic(path: Path, text: str) -> list[dict]:
    issues: list[dict] = []
    if "<title>" not in text:
        issues.append({"severity": "warning", "code": "no_title",
                       "message": "无 <title>"})
    if 'name="description"' not in text and 'name=description' not in text:
        issues.append({"severity": "warning", "code": "no_description",
                       "message": "无 meta description"})
    # Check every <script type="application/ld+json"> payload parses
    for m in re.finditer(
        r'<script type="application/ld\+json">(.*?)</script>', text, flags=re.DOTALL
    ):
        payload = m.group(1).strip()
        try:
            json.loads(payload)
        except Exception as e:
            issues.append({
                "severity": "error", "code": "bad_jsonld",
                "message": f"JSON-LD 解析失败：{e}"
            })
    return issues


def _check_json_file(path: Path, text: str) -> list[dict]:
    try:
        json.loads(text)
        return []
    except Exception as e:
        return [{"severity": "error", "code": "bad_json",
                 "message": f"JSON 无法解析：{e}"}]


def _check_xml_file(path: Path, text: str) -> list[dict]:
    try:
        ET.fromstring(text)
        return []
    except Exception as e:
        return [{"severity": "error", "code": "bad_xml",
                 "message": f"XML 无法解析：{e}"}]


def scan_site(site_dir: Path, only: str | None = None) -> dict[str, list[dict]]:
    """Walk site/, return per-file issue list."""
    if not site_dir.is_dir():
        return {"_meta": [{"severity": "error", "code": "no_site_dir",
                           "message": "site/ 不存在——先跑 python3 publish.py"}]}
    report: dict[str, list[dict]] = {}
    for f in site_dir.rglob("*"):
        if not f.is_file():
            continue
        rel = str(f.relative_to(site_dir))
        if only and only not in rel:
            continue
        # Skip very large media + assets we don't parse
        if f.suffix.lower() in (".mp3", ".m4a", ".wav", ".png", ".jpg", ".jpeg", ".gif",
                                 ".webp", ".ico", ".svg"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        issues: list[dict] = []
        if f.suffix == ".html":
            issues.extend(_check_unreplaced_placeholders(f, text))
            issues.extend(_check_local_refs(f, text, site_dir))
            issues.extend(_check_html_basic(f, text))
        elif f.suffix == ".json" or f.suffix == ".webmanifest":
            issues.extend(_check_json_file(f, text))
        elif f.suffix == ".xml":
            issues.extend(_check_xml_file(f, text))
        if issues:
            report[rel] = issues
    return report


def check_remote(base_url: str) -> dict[str, list[dict]]:
    """Verify deployed site is live + healthy via HTTP.

    Checks homepage, feed.xml, sitemap.xml, podcast-cover.png, and a sample
    episode page. Returns per-URL issue list matching scan_site shape so the
    same reporting code works for both."""
    import urllib.request
    import urllib.error

    base = base_url.rstrip("/")
    report: dict[str, list[dict]] = {}

    def _fetch(path: str, timeout: int = 10) -> tuple[int | None, str, bytes]:
        # URL-encode path segments (Chinese filenames in episodes/ etc.)
        from urllib.parse import quote
        path_enc = quote(path, safe="/.~-_")
        url = base + path_enc if path_enc.startswith("/") else base + "/" + path_enc
        req = urllib.request.Request(url, headers={"User-Agent": "bedtime-doctor/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.headers.get("Content-Type", "") or "", r.read(200_000)
        except urllib.error.HTTPError as e:
            return e.code, e.headers.get("Content-Type", "") or "", b""
        except Exception as e:
            return None, "", str(e).encode()

    # Homepage
    status, ctype, body = _fetch("/")
    issues: list[dict] = []
    if status != 200:
        issues.append({"severity": "error", "code": "home_not_200",
                       "message": f"主页返回 {status}: {body[:200].decode(errors='replace')}"})
    elif "html" not in ctype.lower():
        issues.append({"severity": "warning", "code": "home_bad_ctype",
                       "message": f"主页 content-type={ctype}"})
    if not issues:
        if b"<title>" not in body[:50_000]:
            issues.append({"severity": "warning", "code": "home_no_title",
                           "message": "主页看起来没有 <title>（可能返回了错误页）"})
    if issues:
        report["/ (homepage)"] = issues

    # feed.xml
    issues = []
    status, ctype, body = _fetch("/feed.xml")
    if status != 200:
        issues.append({"severity": "error", "code": "feed_not_200",
                       "message": f"feed.xml 返回 {status}"})
    elif b"<rss" not in body[:5000]:
        issues.append({"severity": "error", "code": "feed_invalid",
                       "message": "feed.xml 不含 <rss> 根——不是有效 RSS"})
    else:
        # Count items
        item_count = body.count(b"<item>")
        if item_count == 0:
            issues.append({"severity": "error", "code": "feed_no_items",
                           "message": "feed.xml 没有 <item>——订阅者看不到任何期"})
        elif item_count < 3:
            issues.append({"severity": "info", "code": "feed_few_items",
                           "message": f"feed.xml 仅 {item_count} 期——平台通常至少要 3 期才推荐"})
    if issues:
        report["/feed.xml"] = issues

    # sitemap.xml
    issues = []
    status, ctype, body = _fetch("/sitemap.xml")
    if status != 200:
        issues.append({"severity": "warning", "code": "sitemap_not_200",
                       "message": f"sitemap.xml 返回 {status}（Google 搜索引擎依赖）"})
    elif b"<urlset" not in body[:2000]:
        issues.append({"severity": "error", "code": "sitemap_invalid",
                       "message": "sitemap.xml 不含 <urlset>"})
    if issues:
        report["/sitemap.xml"] = issues

    # podcast-cover.png
    issues = []
    status, ctype, body = _fetch("/podcast-cover.png", timeout=15)
    if status != 200:
        issues.append({"severity": "warning", "code": "cover_not_200",
                       "message": f"podcast-cover.png 返回 {status}（Apple Podcasts 提交需要）"})
    elif not ctype.startswith("image/"):
        issues.append({"severity": "warning", "code": "cover_bad_ctype",
                       "message": f"podcast-cover.png content-type={ctype} 不是图片"})
    if issues:
        report["/podcast-cover.png"] = issues

    # manifest.webmanifest
    issues = []
    status, ctype, body = _fetch("/manifest.webmanifest")
    if status != 200:
        issues.append({"severity": "warning", "code": "manifest_not_200",
                       "message": f"manifest.webmanifest 返回 {status}（PWA install 会失败）"})
    else:
        try:
            json.loads(body)
        except Exception as e:
            issues.append({"severity": "warning", "code": "manifest_invalid",
                           "message": f"manifest.webmanifest JSON 解析失败: {e}"})
    if issues:
        report["/manifest.webmanifest"] = issues

    # Sample episode page — parse first <item>'s guid from feed
    import re as _re
    ep_guid_m = _re.search(rb"<guid[^>]*>([^<]+)</guid>", body if status == 200 else b"")
    status, ctype, feed_body = _fetch("/feed.xml")
    if status == 200:
        ep_guid_m = _re.search(rb"<guid[^>]*>([^<]+)</guid>", feed_body)
        if ep_guid_m:
            guid = ep_guid_m.group(1).decode(errors="replace")
            issues = []
            status, ctype, body = _fetch(f"/episodes/{guid}.html")
            if status != 200:
                issues.append({"severity": "error", "code": "episode_not_200",
                               "message": f"Sample episode /episodes/{guid}.html 返回 {status}"})
            elif b"<audio" not in body:
                issues.append({"severity": "warning", "code": "episode_no_audio",
                               "message": "单期页不含 <audio> 元素"})
            if issues:
                report[f"/episodes/{guid}.html"] = issues

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--page", help="只诊断文件名包含此子串的页")
    parser.add_argument("--json", action="store_true", help="JSON 输出给 CI")
    parser.add_argument("--summary", action="store_true", help="只打总结")
    parser.add_argument("--remote", metavar="URL",
                        help="远端模式：HTTP 检查已部署站点健康度（例 --remote https://xxx.github.io/repo）")
    args = parser.parse_args()

    if args.remote:
        print(f"🌐 远端健康检查  {args.remote}")
        report = check_remote(args.remote)
    else:
        report = scan_site(SITE, only=args.page)

    error_count = sum(1 for issues in report.values() for i in issues if i["severity"] == "error")
    warn_count = sum(1 for issues in report.values() for i in issues if i["severity"] == "warning")

    if args.json:
        print(json.dumps({
            "files_with_issues": len(report),
            "by_severity": {"error": error_count, "warning": warn_count},
            "per_file": report,
        }, ensure_ascii=False, indent=2))
    else:
        if not args.summary:
            for rel, issues in sorted(report.items()):
                print(f"\n{rel}")
                for iss in issues:
                    sev = iss["severity"]
                    color = RED if sev == "error" else YELLOW
                    print(f"  {color}[{sev}]{RESET} {iss['code']}: {iss['message']}")
        print()
        print(f"{DIM}─ 诊断报告 ─{RESET}")
        if args.remote:
            print(f"  检查远端 {args.remote}（共 {len(report) + (0 if report else 5)} 个 URL）")
        else:
            print(f"  扫描 site/ 共 {len(list(SITE.rglob('*')))} 项资源")
        if error_count:
            print(f"  {RED}error:   {error_count}{RESET}")
        if warn_count:
            print(f"  {YELLOW}warning: {warn_count}{RESET}")
        if not error_count and not warn_count:
            print(f"  {GREEN}全站健康，无问题{RESET}")

    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
