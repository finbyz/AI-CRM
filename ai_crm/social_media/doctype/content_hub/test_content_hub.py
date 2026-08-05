# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestContentHub(FrappeTestCase):
    def test_content_hub_keeps_only_source_and_idea_fields(self):
        """Verify that a content hub stores its source context and generated ideas."""
        meta = frappe.get_meta("Content Hub")

        self.assertEqual(meta.get_field("title").reqd, 1)
        self.assertEqual(meta.get_field("source_type").default, "Manual Topic")
        self.assertEqual(meta.get_field("ideas_child_table").options, "Content Hub Idea")
        self.assertEqual(meta.get_field("generation_status").default, "Queued")
        self.assertIn("Completed", meta.get_field("generation_status").options)
        self.assertNotIn("Ready", meta.get_field("generation_status").options)
        self.assertIsNone(meta.get_field("credential"))
        self.assertIsNone(meta.get_field("platform"))
        self.assertIsNone(meta.get_field("social_media_post"))
