"""TTSManager 降级链测试：mock 所有引擎，验证优先级和降级逻辑。"""
import os
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import asyncio_compat

asyncio_compat.ensure_to_thread()

import stub_engine_imports  # noqa: F401

import tts_engine


class TestTTSManagerFallback(unittest.IsolatedAsyncioTestCase):
    """TTSManager 降级链核心逻辑。"""

    async def test_mimo_succeeds_uses_mimo(self):
        """MiMo 可用且成功时，不调用其他引擎。"""
        manager = tts_engine.TTSManager()
        mimo = manager._engines["mimo"]
        cos = manager._engines["cosyvoice"]

        with patch.object(mimo, "is_available", return_value=True), \
             patch.object(mimo, "synthesize", new_callable=AsyncMock, return_value=True) as mimo_synth, \
             patch.object(cos, "is_available", return_value=True), \
             patch.object(cos, "synthesize", new_callable=AsyncMock) as cos_synth:

            with tempfile.TemporaryDirectory() as td:
                ok = await manager.synthesize("你好", os.path.join(td, "out.mp3"))

        self.assertTrue(ok)
        mimo_synth.assert_called_once()
        cos_synth.assert_not_called()

    async def test_mimo_fails_falls_back_to_cosyvoice(self):
        """MiMo 失败时降级到 CosyVoice。"""
        manager = tts_engine.TTSManager()
        mimo = manager._engines["mimo"]
        cos = manager._engines["cosyvoice"]

        with patch.object(mimo, "is_available", return_value=True), \
             patch.object(mimo, "synthesize", new_callable=AsyncMock, return_value=False), \
             patch.object(cos, "is_available", return_value=True), \
             patch.object(cos, "synthesize", new_callable=AsyncMock, return_value=True) as cos_synth:

            with tempfile.TemporaryDirectory() as td:
                ok = await manager.synthesize("你好", os.path.join(td, "out.mp3"))

        self.assertTrue(ok)
        cos_synth.assert_called_once()

    async def test_all_fail_returns_false(self):
        """所有引擎失败时返回 False。"""
        manager = tts_engine.TTSManager()
        for eng in manager._engines.values():
            patch.object(eng, "is_available", return_value=True).__enter__()
            patch.object(eng, "synthesize", new_callable=AsyncMock, return_value=False).__enter__()

        with tempfile.TemporaryDirectory() as td:
            ok = await manager.synthesize("你好", os.path.join(td, "out.mp3"))

        # cleanup patches
        for eng in manager._engines.values():
            try:
                patch.stopall()
            except Exception:
                pass

        self.assertFalse(ok)

    async def test_unavailable_engine_skipped(self):
        """不可用的引擎被跳过。"""
        manager = tts_engine.TTSManager()
        mimo = manager._engines["mimo"]
        cos = manager._engines["cosyvoice"]
        edge = manager._engines["edge-tts"]

        with patch.object(mimo, "is_available", return_value=False), \
             patch.object(cos, "is_available", return_value=False), \
             patch.object(edge, "is_available", return_value=True), \
             patch.object(edge, "synthesize", new_callable=AsyncMock, return_value=True) as edge_synth:

            with tempfile.TemporaryDirectory() as td:
                ok = await manager.synthesize("你好", os.path.join(td, "out.mp3"))

        self.assertTrue(ok)
        edge_synth.assert_called_once()

    async def test_mimo_exception_falls_back(self):
        """MiMo 抛异常时降级到 CosyVoice（不崩溃）。"""
        manager = tts_engine.TTSManager()
        mimo = manager._engines["mimo"]
        cos = manager._engines["cosyvoice"]

        with patch.object(mimo, "is_available", return_value=True), \
             patch.object(mimo, "synthesize", new_callable=AsyncMock, side_effect=Exception("网络超时")), \
             patch.object(cos, "is_available", return_value=True), \
             patch.object(cos, "synthesize", new_callable=AsyncMock, return_value=True) as cos_synth:

            with tempfile.TemporaryDirectory() as td:
                ok = await manager.synthesize("你好", os.path.join(td, "out.mp3"))

        self.assertTrue(ok)
        cos_synth.assert_called_once()


class TestEdgeTTSEngine(unittest.IsolatedAsyncioTestCase):
    """EdgeTTSEngine 基本功能。"""

    def test_is_available_always_true(self):
        engine = tts_engine.EdgeTTSEngine()
        self.assertTrue(engine.is_available())

    def test_resolve_voice_with_theme(self):
        with patch.dict(tts_engine.THEME_VOICE_MAP, {"测试主题": "zh-CN-XiaoxiaoNeural"}):
            engine = tts_engine.EdgeTTSEngine(theme_name="测试主题")
            self.assertEqual(engine._resolve_voice(), "zh-CN-XiaoxiaoNeural")

    def test_resolve_voice_no_theme_uses_default(self):
        engine = tts_engine.EdgeTTSEngine()
        self.assertEqual(engine._resolve_voice(), tts_engine.EDGE_TTS_DEFAULT)


class TestCosyVoiceModelMapping(unittest.TestCase):
    """_cosyvoice_model_for_voice 音色→模型映射。"""

    def test_default_voice(self):
        self.assertEqual(tts_engine._cosyvoice_model_for_voice("longxiaochun"), "cosyvoice-v1")

    def test_v2_voice(self):
        self.assertEqual(tts_engine._cosyvoice_model_for_voice("custom_v2"), "cosyvoice-v2")

    def test_longanyang(self):
        self.assertEqual(tts_engine._cosyvoice_model_for_voice("longanyang"), "cosyvoice-v3-flash")

    def test_v3_suffix(self):
        self.assertEqual(tts_engine._cosyvoice_model_for_voice("longyue_v3"), "cosyvoice-v3-flash")

    def test_clone_url(self):
        self.assertEqual(
            tts_engine._cosyvoice_model_for_voice("https://example.com/ref.wav"),
            "cosyvoice-clone-v1",
        )


if __name__ == "__main__":
    unittest.main()
