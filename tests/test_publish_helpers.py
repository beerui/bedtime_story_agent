"""Unit tests for publish.py pure helpers.

Not exhaustive — covers the helpers most likely to silently break when the
file is edited (Chinese text parsing, chapter correlation, JSON-LD shape).
Run:  python3 -m unittest tests.test_publish_helpers -v
"""
from __future__ import annotations

import datetime as dt
import json
import unittest

import publish


SAMPLE_STORY = """\
[阶段：引入]
第一段的第一句。[停顿]
第一段的第二句。[停顿]
[环境音：雨声渐近]
第一段的第三句。

[阶段：深入]
[慢速] 深入段慢速句。[停顿1s]
深入段第二句。[停顿]

[阶段：尾声]
[极弱] 尾声第一句。[停顿2s]
[极弱] 尾声第二句。[停顿2s]
"""

SAMPLE_SRT = """\
1
00:00:00,000 --> 00:00:03,000
第一段的第一句。

2
00:00:04,000 --> 00:00:07,000
第一段的第二句。

3
00:00:08,000 --> 00:00:11,000
第一段的第三句。

4
00:00:12,000 --> 00:00:15,000
深入段慢速句。

5
00:00:16,000 --> 00:00:19,000
深入段第二句。

6
00:00:20,000 --> 00:00:23,000
尾声第一句。

7
00:00:24,000 --> 00:00:27,000
尾声第二句。
"""


class TestRenderScriptPlaintext(unittest.TestCase):
    def test_phase_markers_become_bracketed_headings(self):
        out = publish.render_script_plaintext(SAMPLE_STORY)
        self.assertIn("【引入】", out)
        self.assertIn("【深入】", out)
        self.assertIn("【尾声】", out)

    def test_ambient_cues_become_parentheticals(self):
        out = publish.render_script_plaintext(SAMPLE_STORY)
        self.assertIn("（雨声渐近）", out)
        # The bracket form should be gone
        self.assertNotIn("[环境音", out)

    def test_prosody_and_pause_markers_stripped(self):
        out = publish.render_script_plaintext(SAMPLE_STORY)
        self.assertNotIn("[停顿", out)
        self.assertNotIn("[慢速]", out)
        self.assertNotIn("[极弱]", out)

    def test_chapter_title_overrides_replace_phase_names(self):
        titles = {"引入": "承认焦虑", "深入": "指尖棉线", "尾声": "你在这里"}
        out = publish.render_script_plaintext(SAMPLE_STORY, chapter_titles=titles)
        self.assertIn("【承认焦虑】", out)
        self.assertIn("【指尖棉线】", out)
        self.assertIn("【你在这里】", out)
        self.assertNotIn("【引入】", out)

    def test_empty_input_returns_empty(self):
        self.assertEqual(publish.render_script_plaintext(""), "")
        self.assertEqual(publish.render_script_plaintext(None), "")


class TestRenderScriptHtml(unittest.TestCase):
    def test_phases_render_as_h2(self):
        html = publish.render_script_html(SAMPLE_STORY)
        self.assertIn('<h2 class="phase">引入</h2>', html)
        self.assertIn('<h2 class="phase">深入</h2>', html)

    def test_ambient_cues_render_as_em_cue(self):
        html = publish.render_script_html(SAMPLE_STORY)
        self.assertIn('<em class="cue">（雨声渐近）</em>', html)

    def test_narrative_lines_render_as_p(self):
        html = publish.render_script_html(SAMPLE_STORY)
        self.assertIn("<p>第一段的第一句。</p>", html)


class TestExtractChapters(unittest.TestCase):
    def test_correlates_phases_with_srt_cues(self):
        chapters = publish.extract_chapters(SAMPLE_STORY, SAMPLE_SRT)
        self.assertEqual(len(chapters), 3)
        # 引入 starts at cue 0 (00:00:00)
        self.assertEqual(chapters[0]["phase"], "引入")
        self.assertEqual(chapters[0]["start_sec"], 0.0)
        # 深入 starts at cue 3 (00:00:12)
        self.assertEqual(chapters[1]["phase"], "深入")
        self.assertEqual(chapters[1]["start_sec"], 12.0)
        # 尾声 starts at cue 5 (00:00:20)
        self.assertEqual(chapters[2]["phase"], "尾声")
        self.assertEqual(chapters[2]["start_sec"], 20.0)

    def test_title_overrides_applied(self):
        overrides = {"引入": "起", "深入": "承", "尾声": "转"}
        chapters = publish.extract_chapters(SAMPLE_STORY, SAMPLE_SRT, title_overrides=overrides)
        self.assertEqual(chapters[0]["title"], "起")
        self.assertEqual(chapters[2]["title"], "转")
        # phase is still preserved alongside title
        self.assertEqual(chapters[0]["phase"], "引入")

    def test_empty_inputs_return_empty_list(self):
        self.assertEqual(publish.extract_chapters("", SAMPLE_SRT), [])
        self.assertEqual(publish.extract_chapters(SAMPLE_STORY, ""), [])

    def test_chapter_end_times_chain_correctly(self):
        chapters = publish.extract_chapters(SAMPLE_STORY, SAMPLE_SRT)
        # 引入 should end where 深入 starts
        self.assertEqual(chapters[0]["end_sec"], chapters[1]["start_sec"])
        # 尾声 should end at the last cue's end
        self.assertEqual(chapters[2]["end_sec"], 27.0)


class TestBreadcrumbJsonld(unittest.TestCase):
    def test_builds_ordered_list_items(self):
        out = publish._breadcrumb_jsonld([
            ("Home", "/"),
            ("Theme", "/theme/x.html"),
            ("Episode", ""),  # current page, no link
        ])
        self.assertTrue(out.startswith('<script type="application/ld+json">'))
        # Extract JSON payload
        payload = out.replace('<script type="application/ld+json">', '').replace('</script>', '')
        data = json.loads(payload)
        self.assertEqual(data["@type"], "BreadcrumbList")
        items = data["itemListElement"]
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["position"], 1)
        self.assertEqual(items[0]["item"], "/")
        # Last item (current page) has no 'item' URL
        self.assertNotIn("item", items[2])
        self.assertEqual(items[2]["position"], 3)
        self.assertEqual(items[2]["name"], "Episode")

    def test_empty_list_returns_empty_string(self):
        self.assertEqual(publish._breadcrumb_jsonld([]), "")


class TestBuildNewsletterForm(unittest.TestCase):
    def test_disabled_returns_empty(self):
        self.assertEqual(publish._build_newsletter_form({}, "home"), "")
        self.assertEqual(publish._build_newsletter_form({"newsletter": {"enabled": False}}, "home"), "")
        self.assertEqual(publish._build_newsletter_form(
            {"newsletter": {"enabled": True, "endpoint_url": ""}}, "home"
        ), "")

    def test_enabled_renders_form_with_endpoint(self):
        out = publish._build_newsletter_form({
            "newsletter": {
                "enabled": True,
                "endpoint_url": "https://formsubmit.co/hello@example.com",
                "title": "每周精选",
            }
        }, "home")
        self.assertIn('action="https://formsubmit.co/hello@example.com"', out)
        self.assertIn("每周精选", out)
        # honeypot field for bot deflection
        self.assertIn('name="_honey"', out)
        # FormSubmit-specific hidden fields when using formsubmit.co
        self.assertIn('name="_subject"', out)


class TestFmtDuration(unittest.TestCase):
    def test_formats_as_mm_ss(self):
        self.assertEqual(publish._fmt_duration(0), "0:00")
        self.assertEqual(publish._fmt_duration(59), "0:59")
        self.assertEqual(publish._fmt_duration(60), "1:00")
        self.assertEqual(publish._fmt_duration(125), "2:05")
        self.assertEqual(publish._fmt_duration(3600), "60:00")


class TestEsc(unittest.TestCase):
    def test_escapes_html_special_chars(self):
        self.assertEqual(publish._esc("a < b"), "a &lt; b")
        self.assertEqual(publish._esc('say "hi"'), "say &quot;hi&quot;")
        self.assertEqual(publish._esc("tom & jerry"), "tom &amp; jerry")

    def test_none_becomes_empty(self):
        self.assertEqual(publish._esc(None), "")
        self.assertEqual(publish._esc(""), "")


def _mock_episode(folder, theme, title, duration=600, tags=None):
    """Build a minimal episode dict matching scan_episodes shape."""
    return {
        "folder": folder,
        "theme": theme,
        "title": title,
        "description": f"{title} 的描述",
        "tags": tags or [],
        "audio_path": f"outputs/{folder}/final_audio.mp3",
        "audio_abs": f"/abs/outputs/{folder}/final_audio.mp3",
        "audio_size": 1024 * 1024 * 3,
        "duration": duration,
        "word_count": 600,
        "draft": "",
        "draft_full": "",
        "srt": "",
        "chapter_titles": {},
        "timestamp": dt.datetime(2026, 4, 17, 12, 0, 0),
        "pub_date": "Thu, 17 Apr 2026 12:00:00 +0800",
    }


class TestGenerateSitemap(unittest.TestCase):
    def test_includes_all_expected_urls(self):
        eps = [
            _mock_episode("Batch_20260417_120000_午夜慢车", "午夜慢车", "标题"),
        ]
        xml = publish.generate_sitemap(eps, "https://example.com")
        self.assertIn("https://example.com/", xml)
        self.assertIn("/episodes/Batch_20260417_120000_午夜慢车.html", xml)
        self.assertIn("/about.html", xml)
        self.assertIn("/faq.html", xml)
        self.assertIn("/stats.html", xml)


class TestEpisodeSlugAndHref(unittest.TestCase):
    def test_slug_uses_folder_name(self):
        ep = _mock_episode("Batch_20260417_x_title", "theme", "t")
        self.assertEqual(publish._episode_slug(ep), "Batch_20260417_x_title")

    def test_href_points_to_episodes_subdir(self):
        ep = _mock_episode("Batch_abc", "theme", "t")
        self.assertEqual(publish._episode_href(ep), "episodes/Batch_abc.html")


if __name__ == "__main__":
    unittest.main()
