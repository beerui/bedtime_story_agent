"""_synthesize_cosyvoice：mock DashScope，不访问真实 API。"""
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

import asyncio_compat

asyncio_compat.ensure_to_thread()

import stub_engine_imports  # noqa: F401 — 注册桩模块后再加载 engine

import engine


class TestSynthesizeCosyVoice(unittest.IsolatedAsyncioTestCase):
    async def test_writes_audio_and_uses_speech_rate(self):
        mock_instance = MagicMock()
        mock_instance.call.return_value = b"\xff\xf3\xa4fake"

        with patch.dict(
            engine.API_CONFIG,
            {"cosyvoice_api_key": "sk-test", "tts_voice": "longxiaochun"},
            clear=False,
        ):
            with patch.object(engine, "SpeechSynthesizer", return_value=mock_instance) as MockSynth:
                with tempfile.TemporaryDirectory() as td:
                    out = os.path.join(td, "clip.mp3")
                    await engine._synthesize_cosyvoice("睡前一句", out)
                    with open(out, "rb") as f:
                        written = f.read()

        MockSynth.assert_called_once()
        self.assertEqual(
            MockSynth.call_args.kwargs,
            {
                "model": "cosyvoice-v1",
                "voice": "longxiaochun",
                "speech_rate": 0.8,
            },
        )
        mock_instance.call.assert_called_once_with("睡前一句")
        self.assertEqual(written, b"\xff\xf3\xa4fake")

    async def test_model_longanyang_maps_to_v3_flash(self):
        mock_instance = MagicMock()
        mock_instance.call.return_value = b"x"

        with patch.dict(
            engine.API_CONFIG,
            {"cosyvoice_api_key": "sk-test", "tts_voice": "longanyang"},
            clear=False,
        ):
            with patch.object(engine, "SpeechSynthesizer", return_value=mock_instance) as MockSynth:
                with tempfile.TemporaryDirectory() as td:
                    await engine._synthesize_cosyvoice("t", os.path.join(td, "a.mp3"))

        self.assertEqual(MockSynth.call_args.kwargs["model"], "cosyvoice-v3-flash")
        self.assertEqual(MockSynth.call_args.kwargs["voice"], "longanyang")

    async def test_voice_name_with_v2_maps_to_cosyvoice_v2(self):
        mock_instance = MagicMock()
        mock_instance.call.return_value = b"x"

        with patch.dict(
            engine.API_CONFIG,
            {"cosyvoice_api_key": "sk-test", "tts_voice": "custom_v2_voice"},
            clear=False,
        ):
            with patch.object(engine, "SpeechSynthesizer", return_value=mock_instance) as MockSynth:
                with tempfile.TemporaryDirectory() as td:
                    await engine._synthesize_cosyvoice("t", os.path.join(td, "b.mp3"))

        self.assertEqual(MockSynth.call_args.kwargs["model"], "cosyvoice-v2")

    async def test_empty_audio_raises(self):
        mock_instance = MagicMock()
        mock_instance.call.return_value = None

        with patch.dict(
            engine.API_CONFIG,
            {"cosyvoice_api_key": "sk-test", "tts_voice": "longxiaochun"},
            clear=False,
        ):
            with patch.object(engine, "SpeechSynthesizer", return_value=mock_instance):
                with tempfile.TemporaryDirectory() as td:
                    out = os.path.join(td, "c.mp3")
                    with self.assertRaisesRegex(Exception, "CosyVoice"):
                        await engine._synthesize_cosyvoice("t", out)

    async def test_empty_bytes_raises(self):
        mock_instance = MagicMock()
        mock_instance.call.return_value = b""

        with patch.dict(
            engine.API_CONFIG,
            {"cosyvoice_api_key": "sk-test", "tts_voice": "longxiaochun"},
            clear=False,
        ):
            with patch.object(engine, "SpeechSynthesizer", return_value=mock_instance):
                with tempfile.TemporaryDirectory() as td:
                    out = os.path.join(td, "d.mp3")
                    with self.assertRaisesRegex(Exception, "CosyVoice"):
                        await engine._synthesize_cosyvoice("t", out)


if __name__ == "__main__":
    unittest.main()
