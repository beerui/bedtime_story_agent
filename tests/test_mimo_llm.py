#!/usr/bin/env python3
"""MiMo LLM 集成测试：验证 MiMo 优先 + Qwen fallback 逻辑。"""
import unittest
from unittest.mock import MagicMock, patch


class _FakeChoice:
    def __init__(self, content):
        self.message = MagicMock()
        self.message.content = content


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class TestStoryGenFallback(unittest.TestCase):
    """story_gen._llm_raw 和 _llm_call 的 fallback 行为。"""

    @patch("story_gen._mimo_text_client", None)
    @patch("story_gen.text_client")
    def test_no_mimo_uses_qwen(self, mock_qwen):
        mock_qwen.chat.completions.create.return_value = _FakeResponse("qwen reply")
        from story_gen import _llm_raw
        result = _llm_raw("hello")
        self.assertEqual(result, "qwen reply")
        mock_qwen.chat.completions.create.assert_called_once()

    @patch("story_gen.text_client")
    def test_mimo_success_skips_qwen(self, mock_qwen):
        mock_mimo = MagicMock()
        mock_mimo.chat.completions.create.return_value = _FakeResponse("mimo reply")
        import story_gen
        old_client = story_gen._mimo_text_client
        story_gen._mimo_text_client = mock_mimo
        try:
            from story_gen import _llm_raw
            result = _llm_raw("hello")
            self.assertEqual(result, "mimo reply")
            mock_qwen.chat.completions.create.assert_not_called()
        finally:
            story_gen._mimo_text_client = old_client

    @patch("story_gen.text_client")
    def test_mimo_failure_falls_back_to_qwen(self, mock_qwen):
        mock_qwen.chat.completions.create.return_value = _FakeResponse("qwen fallback")
        mock_mimo = MagicMock()
        mock_mimo.chat.completions.create.side_effect = Exception("MiMo API error")
        import story_gen
        old_client = story_gen._mimo_text_client
        story_gen._mimo_text_client = mock_mimo
        try:
            from story_gen import _llm_raw
            result = _llm_raw("hello")
            self.assertEqual(result, "qwen fallback")
            mock_qwen.chat.completions.create.assert_called_once()
        finally:
            story_gen._mimo_text_client = old_client

    @patch("story_gen._mimo_text_client", None)
    @patch("story_gen.text_client")
    def test_both_fail_returns_none(self, mock_qwen):
        mock_qwen.chat.completions.create.side_effect = Exception("Qwen down")
        from story_gen import _llm_raw
        result = _llm_raw("hello")
        self.assertIsNone(result)

    @patch("story_gen._mimo_text_client", None)
    @patch("story_gen.text_client")
    def test_llm_call_raises_on_all_fail(self, mock_qwen):
        mock_qwen.chat.completions.create.side_effect = Exception("down")
        from story_gen import _llm_call
        with self.assertRaises(RuntimeError):
            _llm_call("hello", "test")


_HAS_MOVIEPY = True
try:
    import moviepy.editor  # noqa: F401
except Exception:
    _HAS_MOVIEPY = False


@unittest.skipUnless(_HAS_MOVIEPY, "moviepy/imageio not available")
class TestMetadataGenFallback(unittest.TestCase):
    """metadata_gen._llm_raw 的 fallback 行为。"""

    @patch("metadata_gen._mimo_text_client", None)
    @patch("metadata_gen.text_client")
    def test_no_mimo_uses_qwen(self, mock_qwen):
        mock_qwen.chat.completions.create.return_value = _FakeResponse('{"title":"test"}')
        from metadata_gen import _llm_raw
        result = _llm_raw("hello")
        self.assertEqual(result, '{"title":"test"}')

    @patch("metadata_gen.text_client")
    def test_mimo_success_skips_qwen(self, mock_qwen):
        mock_mimo = MagicMock()
        mock_mimo.chat.completions.create.return_value = _FakeResponse("mimo meta")
        import metadata_gen
        old_client = metadata_gen._mimo_text_client
        metadata_gen._mimo_text_client = mock_mimo
        try:
            from metadata_gen import _llm_raw
            result = _llm_raw("hello")
            self.assertEqual(result, "mimo meta")
            mock_qwen.chat.completions.create.assert_not_called()
        finally:
            metadata_gen._mimo_text_client = old_client


class TestBgmFallback(unittest.TestCase):
    """bgm.select_best_bgm 的 MiMo fallback 行为。"""

    @patch("bgm._mimo_text_client", None)
    @patch("bgm.text_client")
    @patch("os.listdir", return_value=["rain.mp3"])
    def test_no_mimo_uses_qwen(self, mock_ls, mock_qwen):
        mock_qwen.chat.completions.create.return_value = _FakeResponse("LOCAL:rain.mp3")
        from bgm import select_best_bgm
        result = select_best_bgm("雨夜山中小屋")
        self.assertEqual(result, "rain.mp3")

    @patch("bgm.text_client")
    @patch("os.listdir", return_value=["rain.mp3"])
    def test_mimo_success_skips_qwen(self, mock_ls, mock_qwen):
        mock_mimo = MagicMock()
        mock_mimo.chat.completions.create.return_value = _FakeResponse("LOCAL:rain.mp3")
        import bgm
        old_client = bgm._mimo_text_client
        bgm._mimo_text_client = mock_mimo
        try:
            from bgm import select_best_bgm
            result = select_best_bgm("雨夜山中小屋")
            self.assertEqual(result, "rain.mp3")
            mock_qwen.chat.completions.create.assert_not_called()
        finally:
            bgm._mimo_text_client = old_client

    @patch("bgm.text_client")
    @patch("os.listdir", return_value=["rain.mp3"])
    def test_mimo_failure_falls_back(self, mock_ls, mock_qwen):
        mock_mimo = MagicMock()
        mock_mimo.chat.completions.create.side_effect = Exception("MiMo error")
        mock_qwen.chat.completions.create.return_value = _FakeResponse("LOCAL:rain.mp3")
        import bgm
        old_client = bgm._mimo_text_client
        bgm._mimo_text_client = mock_mimo
        try:
            from bgm import select_best_bgm
            result = select_best_bgm("雨夜山中小屋")
            self.assertEqual(result, "rain.mp3")
            mock_qwen.chat.completions.create.assert_called_once()
        finally:
            bgm._mimo_text_client = old_client


class TestConfigMiMoLLM(unittest.TestCase):
    """config.py 中 MiMo LLM 配置项。"""

    def test_mi_base_url_default(self):
        from config import MI_BASE_URL
        self.assertEqual(MI_BASE_URL, "https://token-plan-cn.xiaomimimo.com/v1")

    def test_mi_text_model_default(self):
        from config import MI_TEXT_MODEL
        self.assertEqual(MI_TEXT_MODEL, "mimo-v2.5")

    def test_mi_api_key_loaded(self):
        from config import MI_API_KEY
        # .env 中已配置，应为非空
        self.assertTrue(len(MI_API_KEY) > 0)


if __name__ == "__main__":
    unittest.main()
