"""真实 CosyVoice 语音合成（默认跳过，不 mock）。

在项目根目录执行（需已安装 dashscope、edge_tts、moviepy 等，且 .env 中配置了 COSYVOICE_API_KEY）::

    Windows CMD:
        set RUN_COSYVOICE_LIVE=1
        python -m unittest tests.test_cosyvoice_live -v

    bash:
        RUN_COSYVOICE_LIVE=1 python -m unittest tests.test_cosyvoice_live -v

或使用根目录脚本（无需环境变量）::

    python synthesize_once.py "你要合成的一段话"
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import asyncio_compat

asyncio_compat.ensure_to_thread()

try:
    import engine
except ImportError:
    engine = None

_LIVE_ENABLED = os.environ.get("RUN_COSYVOICE_LIVE") == "1"
_SKIP_REASON = (
    "Set RUN_COSYVOICE_LIVE=1 and install deps, or: python synthesize_once.py \"...\""
)


@unittest.skipUnless(_LIVE_ENABLED and engine is not None, _SKIP_REASON)
class TestCosyVoiceLive(unittest.IsolatedAsyncioTestCase):
    """给固定段落调用 _synthesize_cosyvoice，写入临时文件并校验体积。"""

    async def test_synthesize_sample_paragraph(self):
        from config import API_CONFIG

        if not (API_CONFIG.get("cosyvoice_api_key") or "").strip():
            self.skipTest(".env 中 COSYVOICE_API_KEY 为空")

        sample = (
            "夜深了，列车轻轻摇晃。闭上眼睛，让身体跟着节奏慢慢放松。"
            "外面偶尔掠过一盏灯，像有人轻轻眨了下眼。"
        )

        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "live_sample.mp3")
            await engine._synthesize_cosyvoice(sample, out)

            self.assertTrue(os.path.isfile(out), "应生成音频文件")
            size = os.path.getsize(out)
            self.assertGreater(
                size,
                800,
                f"输出文件过小（{size} bytes），可能合成失败或返回异常数据",
            )


if __name__ == "__main__":
    unittest.main()
