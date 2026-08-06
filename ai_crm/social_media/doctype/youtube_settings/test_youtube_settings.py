# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase

from ai_crm.social_media.doctype.youtube_settings.youtube_settings import YouTubeSettings


class TestYouTubeSettings(FrappeTestCase):
    def test_settings_keep_credentials_private_and_channels_structured(self):
        """Verify that YouTube credentials are secret and channels use child rows."""
        meta = frappe.get_meta("YouTube Settings")

        self.assertEqual(meta.issingle, 1)
        self.assertEqual(meta.get_field("api_key").fieldtype, "Password")
        self.assertEqual(meta.get_field("transcript_io_api_token").fieldtype, "Password")
        self.assertEqual(meta.get_field("channels").options, "YouTube Channel")
        self.assertEqual(meta.get_field("analysis_ai_agent").options, "AI Agent")

    def test_validate_resolves_only_missing_channel_ids(self):
        """Verify that validation resolves a channel ID without replacing an existing ID."""
        settings = object.__new__(YouTubeSettings)
        missing = frappe._dict(channel_name="@missing", channel_id=None)
        existing = frappe._dict(channel_name="@existing", channel_id="UC-existing")
        settings.channels = [missing, existing]

        with patch(
            "ai_crm.social_media.doctype.youtube_settings.youtube_settings.get_channel_id_from_name",
            return_value="UC-resolved",
        ) as resolver:
            settings.validate()

        self.assertEqual(missing.channel_id, "UC-resolved")
        self.assertEqual(existing.channel_id, "UC-existing")
        resolver.assert_called_once_with("@missing")
