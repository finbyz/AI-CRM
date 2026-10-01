# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt

import json
import unittest
from pathlib import Path

from ai_crm.social_media.creative.renderer import render_document, render_slides
from ai_crm.social_media.creative.schema import CreativeValidationError, validate_slides

SAMPLES = Path(__file__).parent / "samples"


def _sample(name):
    return json.loads((SAMPLES / f"{name}.json").read_text())


class TestCreativeSchema(unittest.TestCase):
    def test_samples_pass_strict_validation(self):
        validate_slides(_sample("carousel_month_end_close"), strict=True)
        validate_slides(_sample("single_stat"), strict=True)

    def test_strict_reports_every_problem(self):
        data = {"slides": [
            {"layout": "points", "title": "x" * 80, "items": [{"icon": "nope", "title": "a"}]},
            {"layout": "unknown"},
        ]}
        with self.assertRaises(CreativeValidationError) as ctx:
            validate_slides(data, strict=True)
        errors = " | ".join(ctx.exception.errors)
        self.assertIn("slide 1.title: 80 characters", errors)
        self.assertIn("items needs 2 to 4 entries", errors)
        self.assertIn("icon 'nope'", errors)
        self.assertIn("slide 2: unknown layout", errors)

    def test_lenient_trims_instead_of_failing(self):
        data = {"slides": [{"layout": "cover", "title": "x" * 80, "icon": "nope"}]}
        clean = validate_slides(data, strict=False)
        self.assertEqual(len(clean["slides"][0]["title"]), 60)
        self.assertEqual(clean["slides"][0]["icon"], "sparkle")
        self.assertEqual(len(clean["warnings"]), 2)

    def test_dashes_become_commas(self):
        data = {"slides": [{"layout": "cover", "title": "Fast — and right", "subtitle": "Q1 - Q2, 3–5 days"}]}
        slide = validate_slides(data)["slides"][0]
        self.assertEqual(slide["title"], "Fast, and right")
        self.assertEqual(slide["subtitle"], "Q1, Q2, 3–5 days")


class TestCreativeRenderer(unittest.TestCase):
    def test_carousel_renders_one_png_per_slide(self):
        result = render_slides(_sample("carousel_month_end_close"))
        self.assertEqual(len(result.images), 7)
        self.assertTrue(all(img.startswith(b"\x89PNG") for img in result.images))
        self.assertTrue(result.pdf.startswith(b"%PDF"))
        self.assertEqual(result.warnings, [])

    def test_navy_theme_puts_every_slide_on_navy(self):
        data = _sample("carousel_month_end_close")
        data["slides"][1]["tone"] = "light"  # the model asking for white is overridden
        result = render_slides(data, theme="Navy")
        self.assertNotIn('class="frame slide light', result.html)
        self.assertEqual(result.html.count('class="frame slide dark'), 7)

    def test_ai_text_is_escaped_and_network_is_blocked(self):
        payload = '<img src="https://example.com/x.png"><script>document.title="pwned"</script>'
        result = render_slides({"slides": [{"layout": "cover", "title": "Hi", "subtitle": payload}]})
        self.assertNotIn("<script>document.title", result.html)
        self.assertIn("&lt;script&gt;", result.html)
        self.assertEqual(len(result.images), 1)

    def test_document_renders_single_a4_page(self):
        result = render_document(_sample("one_pager_ai_erp"))
        self.assertEqual(len(result.images), 1)
        self.assertTrue(result.pdf.startswith(b"%PDF"))


class TestCreativeGeneration(unittest.TestCase):
    def setUp(self):
        from ai_crm.social_media.creative import generation

        self.gen = generation

    def _fake(self, replies):
        calls = []

        def invoke(messages):
            calls.append(list(messages))
            return replies[len(calls) - 1]

        return invoke, calls

    def test_prompt_carries_rules_brief_and_example(self):
        system, user = self.gen.build_messages(
            "Carousel", "GST e-invoicing", title="E-invoice", post_text="Body",
            instructions="Talk to CFOs", brand_voice="Plain", example={"slides": []}, min_slides=6, max_slides=8,
            skill="# FinByz skill\nLess to read, more to see.",
        )
        self.assertIn("Less to read, more to see.", system)
        self.assertIn("6 to 8 slides", system)
        self.assertIn("Talk to CFOs", system)
        self.assertIn("Never invent statistics", system)
        self.assertIn("fictional", system)
        self.assertIn("GST e-invoicing", user)
        self.assertIn("Body", user)

    def test_valid_reply_is_accepted_first_time(self):
        reply = "```json\n" + json.dumps(_sample("carousel_month_end_close")) + "\n```"
        invoke, calls = self._fake([reply])
        content, warnings = self.gen.write_content(invoke, "Carousel", "s", "u", 5, 8)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(content["slides"]), 7)
        self.assertEqual(warnings, [])

    def test_bad_reply_gets_one_correction_round(self):
        bad = json.dumps({"slides": [{"layout": "points", "title": "x"}]})
        good = json.dumps(_sample("single_stat"))
        invoke, calls = self._fake([bad, good])
        content, _ = self.gen.write_content(invoke, "Single Image", "s", "u")
        self.assertEqual(len(calls), 2)
        self.assertIn("Fix these problems", calls[1][-1][1])
        self.assertEqual(content["slides"][0]["layout"], "stats")

    def test_still_bad_after_retry_is_trimmed_not_failed(self):
        long_title = {"slides": [{"layout": "cover", "title": "y" * 90}]}
        invoke, calls = self._fake([json.dumps(long_title)] * 2)
        content, warnings = self.gen.write_content(invoke, "Single Image", "s", "u")
        self.assertEqual(len(calls), 2)
        self.assertEqual(len(content["slides"][0]["title"]), 60)
        self.assertTrue(warnings)

    def test_carousel_must_open_with_cover_and_close_with_cta(self):
        data = {"slides": [_sample("carousel_month_end_close")["slides"][1]] * 5}
        with self.assertRaises(CreativeValidationError) as ctx:
            self.gen.check_content("Carousel", data, True, 5, 8)
        self.assertIn("the first slide must use the cover layout", ctx.exception.errors)
