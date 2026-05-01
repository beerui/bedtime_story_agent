"""mimo_tts.py 单元测试：mock MiMo API 响应，不访问真实 API。"""
import base64
import os
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

# mimo_tts.py 只依赖 openai 和 config，不依赖 moviepy 等重依赖，
# 但 config.py 会在 import 时加载 .env 和 certifi，需确保不报错。
import mimo_tts


def _make_mock_response(audio_bytes: bytes = b"\xff\xf3\xa4fake"):
    """构造一个模拟的 MiMo API 响应对象。"""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_audio = MagicMock()
    mock_audio.data = base64.b64encode(audio_bytes).decode("utf-8")
    mock_choice.message.audio = mock_audio
    mock_response.choices = [mock_choice]
    return mock_response


class TestSynthesizeMimo(unittest.TestCase):
    """synthesize_mimo 核心功能测试。"""

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_preset_voice_success(self):
        """预置音色模式：成功合成并写入文件。"""
        fake_audio = b"\xff\xf3\xa4\x00fake_wav_data"
        mock_response = _make_mock_response(fake_audio)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                result = mimo_tts.synthesize_mimo("你好世界", out, voice="冰糖")

        self.assertTrue(result)
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-tts")
        self.assertEqual(call_kwargs["extra_body"]["audio"]["voice"], "冰糖")
        self.assertEqual(call_kwargs["extra_body"]["audio"]["format"], "wav")
        self.assertFalse(call_kwargs["stream"])

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_voice_design_mode(self):
        """Voice Design 模式：voice 参数作为音色描述，自动选择 voicedesign 模型。"""
        fake_audio = b"\x00" * 100
        mock_response = _make_mock_response(fake_audio)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                result = mimo_tts.synthesize_mimo(
                    "睡前故事",
                    out,
                    voice="一个温柔磁性的年轻女声，像在耳边低语",
                )

        self.assertTrue(result)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-tts-voicedesign")

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_explicit_model_override(self):
        """显式指定 model 参数时，自动选择被覆盖。"""
        mock_response = _make_mock_response(b"\x00" * 50)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                result = mimo_tts.synthesize_mimo(
                    "测试", out, voice="冰糖", model="mimo-v2.5-tts-voicedesign"
                )

        self.assertTrue(result)
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-tts-voicedesign")

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_style_included_in_user_content(self):
        """style 参数应包含在 user content 中。"""
        mock_response = _make_mock_response(b"\x00" * 50)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                mimo_tts.synthesize_mimo("测试", out, voice="冰糖", style="温柔慵懒")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        self.assertEqual(messages[0]["role"], "user")
        self.assertIn("温柔慵懒", messages[0]["content"])
        self.assertEqual(messages[1]["role"], "assistant")
        self.assertEqual(messages[1]["content"], "测试")

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_voice_design_with_style(self):
        """Voice Design 模式下，style 应拼接到音色描述后。"""
        mock_response = _make_mock_response(b"\x00" * 50)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                mimo_tts.synthesize_mimo(
                    "测试", out,
                    voice="温柔女声",
                    style="缓慢低语",
                )

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        messages = call_kwargs["messages"]
        self.assertIn("温柔女声", messages[0]["content"])
        self.assertIn("缓慢低语", messages[0]["content"])

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_no_voice_defaults_to_preset(self):
        """voice=None 时应使用预置音色模型和默认音色。"""
        mock_response = _make_mock_response(b"\x00" * 50)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                mimo_tts.synthesize_mimo("测试", out)

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-tts")
        self.assertEqual(call_kwargs["extra_body"]["audio"]["voice"], "冰糖")

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_unknown_voice_in_preset_model_uses_default(self):
        """预置音色模型中，未知 voice 应降级到默认音色。"""
        mock_response = _make_mock_response(b"\x00" * 50)

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                out = os.path.join(td, "voice.wav")
                mimo_tts.synthesize_mimo("测试", out, voice="不存在的音色")

        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        # voice 不在预置表中 → 自动选择 voicedesign 模型
        self.assertEqual(call_kwargs["model"], "mimo-v2.5-tts-voicedesign")


class TestSynthesizeMimoFailure(unittest.TestCase):
    """失败场景测试：确保不抛异常，返回 False。"""

    @patch.object(mimo_tts, "MI_API_KEY", "")
    def test_missing_api_key_returns_false(self):
        """未配置 MI_API_KEY 时返回 False。"""
        with tempfile.TemporaryDirectory() as td:
            result = mimo_tts.synthesize_mimo("测试", os.path.join(td, "out.wav"))
        self.assertFalse(result)

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_empty_text_returns_false(self):
        """空文本返回 False。"""
        with tempfile.TemporaryDirectory() as td:
            result = mimo_tts.synthesize_mimo("", os.path.join(td, "out.wav"))
        self.assertFalse(result)

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_api_exception_returns_false(self):
        """API 调用抛异常时返回 False。"""
        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.side_effect = Exception("网络超时")
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                result = mimo_tts.synthesize_mimo("测试", os.path.join(td, "out.wav"))
        self.assertFalse(result)

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_empty_audio_response_returns_false(self):
        """API 返回空音频数据时返回 False。"""
        mock_response = MagicMock()
        mock_response.choices = []

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                result = mimo_tts.synthesize_mimo("测试", os.path.join(td, "out.wav"))
        self.assertFalse(result)

    @patch.object(mimo_tts, "MI_API_KEY", "sk-test-mimo")
    def test_none_audio_data_returns_false(self):
        """API 返回 audio.data 为 None 时返回 False。"""
        mock_response = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.audio.data = None
        mock_response.choices = [mock_choice]

        with patch.object(mimo_tts, "OpenAI") as MockOpenAI:
            mock_client = MagicMock()
            mock_client.chat.completions.create.return_value = mock_response
            MockOpenAI.return_value = mock_client

            with tempfile.TemporaryDirectory() as td:
                result = mimo_tts.synthesize_mimo("测试", os.path.join(td, "out.wav"))
        self.assertFalse(result)


class TestResolveStyleForProgress(unittest.TestCase):
    """resolve_style_for_progress 分段映射测试。"""

    def test_progress_0_0(self):
        style = mimo_tts.resolve_style_for_progress(0.0)
        self.assertIn("自然平静", style)

    def test_progress_0_14(self):
        style = mimo_tts.resolve_style_for_progress(0.14)
        self.assertIn("自然平静", style)

    def test_progress_0_15(self):
        style = mimo_tts.resolve_style_for_progress(0.15)
        self.assertIn("温暖柔和", style)

    def test_progress_0_25(self):
        style = mimo_tts.resolve_style_for_progress(0.25)
        self.assertIn("温暖柔和", style)

    def test_progress_0_4(self):
        style = mimo_tts.resolve_style_for_progress(0.4)
        self.assertIn("轻柔缓慢", style)

    def test_progress_0_6(self):
        style = mimo_tts.resolve_style_for_progress(0.6)
        self.assertIn("缓慢低沉", style)

    def test_progress_0_8(self):
        style = mimo_tts.resolve_style_for_progress(0.8)
        self.assertIn("极轻极慢", style)

    def test_progress_0_9(self):
        style = mimo_tts.resolve_style_for_progress(0.9)
        self.assertIn("几乎听不见", style)

    def test_progress_1_0(self):
        style = mimo_tts.resolve_style_for_progress(1.0)
        self.assertIn("几乎听不见", style)


class TestMapInlineTagToAudioTag(unittest.TestCase):
    """内联标记到 MiMo 音频标签的映射测试。"""

    def test_slow(self):
        self.assertEqual(mimo_tts.map_inline_tag_to_audio_tag("慢速"), "缓慢")

    def test_quiet(self):
        self.assertEqual(mimo_tts.map_inline_tag_to_audio_tag("轻声"), "轻声")

    def test_very_weak(self):
        self.assertEqual(mimo_tts.map_inline_tag_to_audio_tag("极弱"), "极轻低语")

    def test_unknown_tag(self):
        self.assertIsNone(mimo_tts.map_inline_tag_to_audio_tag("未知标记"))


if __name__ == "__main__":
    unittest.main()
