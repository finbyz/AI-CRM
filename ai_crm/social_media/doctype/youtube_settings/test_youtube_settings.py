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

    def test_validate_resolves_new_or_renamed_channels_only(self):
        """Verify that validation looks up new or renamed channels and keeps resolved ones."""
        settings = frappe.get_doc({
            "doctype": "YouTube Settings",
            "channels": [
                {"name": "row-new", "channel_name": "@new"},
                {"name": "row-kept", "channel_name": "@kept", "channel_id": "UC-kept", "channel_title": "Kept"},
            ],
        })
        before = frappe._dict(channels=[frappe._dict(name="row-kept", channel_name="@kept")])

        with (
            patch.object(settings, "get_doc_before_save", return_value=before),
            patch(
                "ai_crm.social_media.doctype.youtube_settings.youtube_settings.get_channel_info",
                return_value={"channel_id": "UC-new", "title": "New"},
            ) as lookup,
        ):
            settings.validate()

        self.assertEqual(settings.channels[0].channel_id, "UC-new")
        self.assertEqual(settings.channels[0].channel_title, "New")
        self.assertEqual(settings.channels[1].channel_id, "UC-kept")
        lookup.assert_called_once_with("@new", None)

    def test_validate_rejects_unknown_channel(self):
        """Verify that saving fails when a channel handle cannot be found."""
        settings = frappe.get_doc({"doctype": "YouTube Settings", "channels": [{"channel_name": "@nope"}]})

        with (
            patch.object(settings, "get_doc_before_save", return_value=None),
            patch(
                "ai_crm.social_media.doctype.youtube_settings.youtube_settings.get_channel_info",
                return_value=None,
            ),
            self.assertRaises(frappe.ValidationError),
        ):
            settings.validate()

    def test_validate_keeps_unchanged_legacy_row_without_title(self):
        """Verify that a saved row without a title is looked up by its ID and never blocks the save."""
        settings = frappe.get_doc({
            "doctype": "YouTube Settings",
            "channels": [{"name": "row-old", "channel_name": "Finbyz Tech", "channel_id": "UC-old"}],
        })
        before = frappe._dict(channels=[frappe._dict(name="row-old", channel_name="Finbyz Tech")])

        with (
            patch.object(settings, "get_doc_before_save", return_value=before),
            patch(
                "ai_crm.social_media.doctype.youtube_settings.youtube_settings.get_channel_info",
                return_value=None,
            ) as lookup,
        ):
            settings.validate()

        self.assertEqual(settings.channels[0].channel_id, "UC-old")
        self.assertEqual(settings.channels[0].channel_title, "Finbyz Tech")
        lookup.assert_called_once_with("UC-old", None)

    def test_validate_resets_checkpoint_when_channel_changes(self):
        """Verify that replacing a row's channel clears its last fetched time."""
        settings = frappe.get_doc({
            "doctype": "YouTube Settings",
            "channels": [{
                "name": "row-1", "channel_name": "@new", "channel_id": "UC-old",
                "channel_title": "Old", "last_fetched_on": "2026-10-01 10:00:00",
            }],
        })
        before = frappe._dict(channels=[frappe._dict(name="row-1", channel_name="@old")])

        with (
            patch.object(settings, "get_doc_before_save", return_value=before),
            patch(
                "ai_crm.social_media.doctype.youtube_settings.youtube_settings.get_channel_info",
                return_value={"channel_id": "UC-new", "title": "New"},
            ),
        ):
            settings.validate()

        self.assertEqual(settings.channels[0].channel_id, "UC-new")
        self.assertIsNone(settings.channels[0].last_fetched_on)
