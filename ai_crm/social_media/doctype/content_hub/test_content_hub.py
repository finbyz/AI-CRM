# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_crm.social_media.doctype.content_hub import generation
from ai_crm.social_media.doctype.content_hub.research import _format_sources


class TestContentHub(FrappeTestCase):
    def test_content_hub_keeps_source_research_and_idea_fields(self):
        """Verify that a content hub stores its source context, research and (hidden) ideas."""
        meta = frappe.get_meta("Content Hub")

        self.assertEqual(meta.get_field("title").reqd, 1)
        self.assertEqual(meta.get_field("source_type").default, "Manual Topic")
        self.assertEqual(meta.get_field("ideas_child_table").options, "Content Hub Idea")
        self.assertEqual(meta.get_field("generation_status").default, "Queued")
        self.assertIn("Completed", meta.get_field("generation_status").options)
        self.assertEqual(meta.get_field("research").fieldtype, "Markdown Editor")
        self.assertIn("Researching", meta.get_field("research_status").options)
        self.assertIsNone(meta.get_field("credential"))
        self.assertIsNone(meta.get_field("platform"))
        self.assertIsNone(meta.get_field("social_media_post"))

    def test_research_sources_are_listed_once_without_markup(self):
        """Verify that web citations become a clean, de-duplicated source list."""
        citation = {"type": "url_citation", "url_citation": {"url": "https://a.com", "title": "A [x]<!-- -->"}}

        text = _format_sources([citation, citation, {"type": "other"}])

        self.assertEqual(text, "\n\n## Sources\n1. [A x](https://a.com)")
        self.assertEqual(_format_sources([]), "")

    def test_post_from_research_sends_research_and_picks_its_own_angle(self):
        """Verify that a research-based post gets the research and no pre-selected idea."""
        hub = frappe._dict(
            name="CONT-HUB-T", title="Netflix buys an AI studio", target_audience="", source_type="Manual Topic",
            channel_name="", source_url="", research="## Summary\nNetflix paid $587M.", ideas_child_table=[],
        )
        post = frappe._dict(credential_type="LinkedIn Integration")

        with patch.object(generation.frappe, "get_single", return_value=frappe._dict(brand_voice="")):
            values = generation._build_agent_input(hub, post, None)
        message = generation._build_research_message(hub, "Focus on CFOs")

        self.assertEqual(values["idea_title"], hub.title)
        self.assertIn("No idea was pre-selected", values["idea_description"])
        self.assertIn("Netflix paid $587M.", message)
        self.assertIn("Extra instructions for this post: Focus on CFOs", message)
        self.assertEqual(generation._build_research_message(frappe._dict(research="")), "Write the post.")

    def test_post_agent_sees_what_the_account_already_published(self):
        """Verify that the account's earlier posts are sent so the agent changes the angle or skips."""
        post = frappe._dict(name="SMP-NEW", credential_type="LinkedIn Integration", credential="Acc")
        earlier = frappe._dict(content="Netflix paid $587M.", status="Posted", posted_on="2026-10-01", modified=None)

        with patch.object(generation.frappe, "get_all", return_value=[earlier]) as get_all:
            message = generation._build_history_message(post)

        filters = get_all.call_args.kwargs["filters"]
        self.assertEqual((filters["credential_type"], filters["credential"]), ("LinkedIn Integration", "Acc"))
        self.assertNotIn("Draft", filters["status"][1])
        self.assertEqual(filters["name"], ["!=", "SMP-NEW"])
        self.assertIn("Netflix paid $587M.", message)
        self.assertIn('{"content": "SKIP:', message)
        with patch.object(generation.frappe, "get_all", return_value=[]):
            self.assertEqual(generation._build_history_message(post), "")

    def test_skipped_topic_marks_the_post_failed_with_the_reason(self):
        """Verify that a SKIP reply never becomes post content."""
        post = frappe._dict(name="SMP-NEW", credential_type="LinkedIn Integration", db_set=lambda *a, **k: None)
        hub = frappe._dict(name="CONT-HUB-T", ideas_child_table=[], research="")
        agent = frappe._dict(invoke=lambda **kwargs: {"content": "SKIP: post [1] already made this point"})

        with (
            patch.object(generation.frappe, "get_doc", side_effect=[post, hub]),
            patch.object(generation, "_get_post_agent", return_value=agent),
            patch.object(generation, "_build_agent_input", return_value={}),
            patch.object(generation, "_build_history_message", return_value=""),
            patch.object(generation, "_mark_generation_failed") as mark_failed,
        ):
            generation.generate_post_content("SMP-NEW", "CONT-HUB-T", "research-abc")

        self.assertIn("already covered this topic", mark_failed.call_args.args[1])
        self.assertIn("post [1] already made this point", mark_failed.call_args.args[1])

    def test_web_page_holds_the_full_research(self):
        """Verify that a web page or blog draft carries the complete research, unpublished."""
        hub = frappe._dict(title="Netflix buys an AI studio", research="## Summary\nNetflix paid $587M.\n\n## Sources\n1. [A](https://a.com)")

        with patch("ai_crm.social_media.doctype.content_hub.research.generate_page_title", return_value="Why Netflix Paid $587M for AI Studio Tools"):
            page = generation.draft_nextjs_page(hub, "Blog Post")

        self.assertFalse(page.name and frappe.db.exists("NextJS Page", page.name))
        self.assertEqual(page.page_type, "Blog Post")
        self.assertEqual(page.content_type, "Markdown")
        self.assertEqual(page.content_md, hub.research)
        self.assertEqual(page.is_published, 0)
        self.assertEqual(page.title, "Why Netflix Paid $587M for AI Studio Tools")
        self.assertEqual(page.route, "/why-netflix-paid-587m-for-ai-studio-tools")
        with self.assertRaises(frappe.ValidationError):
            generation.draft_nextjs_page(frappe._dict(title="x", research=""), "Web Page")

    def test_page_title_never_reuses_the_source_title(self):
        """Verify that a saved page title is reused, but one matching the source title is rewritten."""
        hub = frappe._dict(title="NEW Claude Obsidian is an ACTUAL GAME CHANGER!", page_title="Our own headline", research="notes")
        with patch("ai_crm.social_media.doctype.content_hub.research.generate_page_title", return_value="Fresh") as generate:
            self.assertEqual(generation._get_page_title(hub, "Blog Post"), "Our own headline")
            generate.assert_not_called()

            hub.page_title = "new claude obsidian is an actual game changer"
            self.assertEqual(generation._get_page_title(hub, "Blog Post"), "Fresh")
            self.assertEqual(generate.call_args.args[1], hub.title)
