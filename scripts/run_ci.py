#!/usr/bin/env python3
"""
CI 门禁脚本 — 运行所有质量检查。
退出码 0 = 全部通过，退出码 1 = 有失败。
"""
import subprocess
import sys

def run_check(name, cmd):
    print(f"\n{'='*60}")
    print(f"[CHECK] {name}")
    print('='*60)
    result = subprocess.run(cmd, shell=True, capture_output=False)
    if result.returncode != 0:
        print(f"[FAIL] {name}")
        return False
    print(f"[PASS] {name}")
    return True

def main():
    checks = []

    # 1. Golden rules (通用检查)
    checks.append(run_check(
        "Golden Rules",
        f"{sys.executable} scripts/golden_rules.py ."
    ))

    # 2. Unit tests
    checks.append(run_check(
        "Unit Tests",
        f"{sys.executable} -m unittest tests.test_cosyvoice_synthesize tests.test_prosody tests.test_mimo_tts tests.test_mimo_llm tests.test_tts_manager tests.test_publish_helpers -v"
    ))

    # Summary
    passed = sum(checks)
    total = len(checks)
    print(f"\n{'='*60}")
    print(f"CI Summary: {passed}/{total} checks passed")
    print('='*60)

    sys.exit(0 if all(checks) else 1)

if __name__ == "__main__":
    main()
