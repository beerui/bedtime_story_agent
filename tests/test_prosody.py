"""ProsodyCurve 插值与 apply_curve_to_blocks 单元测试。"""
import unittest

from prosody import (
    ProsodyCurve,
    apply_curve_to_blocks,
    parse_silence,
    parse_phase_marker,
    TAG_MULTIPLIERS,
)

SAMPLE_CURVE = {
    "speed":  [(0.0, 1.0), (0.5, 0.8), (1.0, 0.5)],
    "volume": [(0.0, 1.0), (0.5, 0.7), (1.0, 0.3)],
    "pause":  [(0.0, 0.3), (0.5, 0.8), (1.0, 2.0)],
}


class TestProsodyCurve(unittest.TestCase):
    def setUp(self):
        self.curve = ProsodyCurve(SAMPLE_CURVE)

    def test_interpolate_start(self):
        s, v, p = self.curve.interpolate(0.0)
        self.assertAlmostEqual(s, 1.0)
        self.assertAlmostEqual(v, 1.0)
        self.assertAlmostEqual(p, 0.3)

    def test_interpolate_end(self):
        s, v, p = self.curve.interpolate(1.0)
        self.assertAlmostEqual(s, 0.5)
        self.assertAlmostEqual(v, 0.3)
        self.assertAlmostEqual(p, 2.0)

    def test_interpolate_mid(self):
        s, v, p = self.curve.interpolate(0.5)
        self.assertAlmostEqual(s, 0.8)
        self.assertAlmostEqual(v, 0.7)
        self.assertAlmostEqual(p, 0.8)

    def test_interpolate_quarter(self):
        s, v, p = self.curve.interpolate(0.25)
        self.assertAlmostEqual(s, 0.9)
        self.assertAlmostEqual(v, 0.85)
        self.assertAlmostEqual(p, 0.55)

    def test_interpolate_clamp_below(self):
        s, v, p = self.curve.interpolate(-0.5)
        self.assertAlmostEqual(s, 1.0)

    def test_interpolate_clamp_above(self):
        s, v, p = self.curve.interpolate(1.5)
        self.assertAlmostEqual(s, 0.5)


class TestParseSilence(unittest.TestCase):
    def test_pause_plain(self):
        self.assertAlmostEqual(parse_silence("[停顿]"), 0.8)

    def test_pause_ms(self):
        self.assertAlmostEqual(parse_silence("[停顿500ms]"), 0.5)

    def test_pause_s(self):
        self.assertAlmostEqual(parse_silence("[停顿2s]"), 2.0)

    def test_env_sound(self):
        self.assertAlmostEqual(parse_silence("[环境音：雨声]"), 4.0)

    def test_non_pause(self):
        self.assertIsNone(parse_silence("[慢速]"))

    def test_brackets_variant(self):
        self.assertAlmostEqual(parse_silence("【停顿】"), 0.8)
        self.assertAlmostEqual(parse_silence("【停顿1s】"), 1.0)


class TestParsePhaseMarker(unittest.TestCase):
    def test_parse_intro(self):
        self.assertEqual(parse_phase_marker("[阶段：引入]"), "引入")

    def test_parse_deep(self):
        self.assertEqual(parse_phase_marker("[阶段：深入]"), "深入")

    def test_parse_ending(self):
        self.assertEqual(parse_phase_marker("【阶段：尾声】"), "尾声")

    def test_non_phase(self):
        self.assertIsNone(parse_phase_marker("[停顿]"))


class TestApplyCurveToBlocks(unittest.TestCase):
    def setUp(self):
        self.curve = ProsodyCurve(SAMPLE_CURVE)

    def test_basic_two_blocks(self):
        blocks = [
            {"type": "speech", "text": "你好"},
            {"type": "speech", "text": "晚安"},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        # First speech block: progress=0.0, speed=1.0
        speech_blocks = [b for b in result if b["type"] == "speech"]
        self.assertEqual(len(speech_blocks), 2)
        self.assertAlmostEqual(speech_blocks[0]["speed"], 1.0)
        self.assertAlmostEqual(speech_blocks[1]["speed"], 0.5)
        # Should have an auto_pause between them
        auto_pauses = [b for b in result if b["type"] == "auto_pause"]
        self.assertEqual(len(auto_pauses), 1)

    def test_multiplier_applied(self):
        blocks = [
            {"type": "speech", "text": "你好", "multiplier": TAG_MULTIPLIERS["极弱"]},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        speech = [b for b in result if b["type"] == "speech"][0]
        # Single block → progress=0.0, curve speed=1.0, vol=1.0
        # 极弱 multiplier: speed*0.7, vol*0.3
        self.assertAlmostEqual(speech["speed"], 1.0 * 0.7)
        self.assertAlmostEqual(speech["vol"], 1.0 * 0.3)

    def test_phase_markers_affect_progress(self):
        blocks = [
            {"type": "phase_marker", "phase": "引入"},
            {"type": "speech", "text": "A"},
            {"type": "speech", "text": "B"},
            {"type": "phase_marker", "phase": "尾声"},
            {"type": "speech", "text": "C"},
            {"type": "speech", "text": "D"},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        speech_blocks = [b for b in result if b["type"] == "speech"]
        self.assertEqual(len(speech_blocks), 4)
        # A is at progress 0.0, B between 0.0 and 0.7, C at ~0.7, D at 1.0
        self.assertAlmostEqual(speech_blocks[0]["progress"], 0.0)
        self.assertAlmostEqual(speech_blocks[3]["progress"], 1.0)
        # C should be around 0.7 (尾声 anchor)
        self.assertGreaterEqual(speech_blocks[2]["progress"], 0.65)

    def test_paragraph_start_scales_pause(self):
        blocks = [
            {"type": "speech", "text": "A"},
            {"type": "speech", "text": "B", "paragraph_start": True},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        auto_pauses = [b for b in result if b["type"] == "auto_pause"]
        self.assertEqual(len(auto_pauses), 1)
        # Paragraph pause should be 1.5x the base pause
        base_pause = self.curve.interpolate(1.0)[2]  # progress of B = 1.0
        self.assertAlmostEqual(auto_pauses[0]["sec"], base_pause * 1.5)

    def test_pure_breaks_preserved(self):
        blocks = [
            {"type": "speech", "text": "A"},
            {"type": "pure_break", "sec": 2.0, "raw": "[停顿2s]"},
            {"type": "speech", "text": "B"},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        pure = [b for b in result if b["type"] == "pure_break"]
        self.assertEqual(len(pure), 1)
        self.assertAlmostEqual(pure[0]["sec"], 2.0)

    def test_empty_blocks(self):
        result = apply_curve_to_blocks([], self.curve)
        self.assertEqual(result, [])

    def test_phase_markers_stripped(self):
        blocks = [
            {"type": "phase_marker", "phase": "引入"},
            {"type": "speech", "text": "A"},
        ]
        result = apply_curve_to_blocks(blocks, self.curve)
        self.assertFalse(any(b["type"] == "phase_marker" for b in result))


if __name__ == "__main__":
    unittest.main()
