# Copyright (c) 2026, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestYouTubeVideo(FrappeTestCase):
    def test_video_row_stores_source_analysis_and_content_hub_link(self):
        """Verify that an imported video retains source data, analysis, and its content hub link."""
        meta = frappe.get_meta("YouTube Video")

        self.assertEqual(meta.istable, 1)
        for fieldname in ("channel_id", "video_id", "title", "video_link"):
            self.assertEqual(meta.get_field(fieldname).reqd, 1)
        self.assertEqual(meta.get_field("content_hub").options, "Content Hub")
        self.assertEqual(meta.get_field("transcript").fieldtype, "Long Text")
        self.assertIsNone(meta.get_field("social_media_post"))
