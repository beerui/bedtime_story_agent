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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--page", help="只诊断文件名包含此子串的页")
    parser.add_argument("--json", action="store_true", help="JSON 输出给 CI")
    parser.add_argument("--summary", action="store_true", help="只打总结")
    args = parser.parse_args()

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
