# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestContentHubSetting(FrappeTestCase):
    def test_settings_define_agents_and_current_brand_voice(self):
        """Verify that content generation uses central agents and the current brand voice."""
        meta = frappe.get_meta("Content Hub Setting")
        agent_fields = {
            "idea_generator_agent",
            "post_generator_agent",
            "youtube_idea_generator_agent",
            "youtube_post_generator_agent",
            "revise_post_agent",
            "image_generation_agent",
            "helper_agent",
        }

        self.assertEqual(meta.issingle, 1)
        for fieldname in agent_fields:
            field = meta.get_field(fieldname)
            self.assertEqual(field.fieldtype, "Link")
            self.assertEqual(field.options, "AI Agent")
        self.assertEqual(meta.get_field("brand_voice").fieldtype, "Long Text")
        self.assertIsNone(meta.get_field("youtube_fetch_agent"))
