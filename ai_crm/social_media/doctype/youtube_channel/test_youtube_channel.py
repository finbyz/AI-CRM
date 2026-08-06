# Copyright (c) 2026, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestYouTubeChannel(FrappeTestCase):
    def test_channel_row_has_only_fetch_configuration(self):
        """Verify that each channel row stores the identity and fetch schedule."""
        meta = frappe.get_meta("YouTube Channel")

        self.assertEqual(meta.istable, 1)
        self.assertEqual(meta.get_field("channel_name").reqd, 1)
        self.assertEqual(meta.get_field("channel_id").reqd, 1)
        self.assertEqual(meta.get_field("fetch_frequency").default, "1")
        self.assertEqual(meta.get_field("last_fetched_on").read_only, 1)
