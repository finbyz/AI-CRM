# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import add_to_date, now_datetime

from ai_crm.social_media.doctype.social_media_post.social_media_post import SocialMediaPost


class TestSocialMediaPost(FrappeTestCase):
    def test_schema_uses_credentials_without_redundant_snapshots(self):
        """Verify that a post derives its platform and keeps source data in Content Hub."""
        meta = frappe.get_meta("Social Media Post")
        removed_fields = {
            "platform",
            "source_title",
            "source_channel",
            "source_video_link",
            "source_views",
            "source_transcript",
            "source_idea_description",
            "brand_voice_snapshot",
        }

        self.assertEqual(meta.get_field("credential").options, "credential_type")
        self.assertEqual(meta.get_field("content_hub").options, "Content Hub")
        for fieldname in removed_fields:
            self.assertIsNone(meta.get_field(fieldname))

    def test_platform_property_uses_credential_type(self):
        """Verify that the post platform is derived from its credential DocType."""
        post = self.make_post(credential_type="Twitter Integration")

        self.assertEqual(post.platform, "X (Twitter)")

    def make_post(self, **values):
        data = {
            "doctype": "Social Media Post",
            "title": "A draft",
            "content": "Original content",
            "credential_type": "LinkedIn Integration",
            "credential": "Test Account",
            "status": "Draft",
            "generation_status": "Ready",
        }
        data.update(values)
        return frappe.get_doc(data)

    def test_approved_content_change_returns_post_to_draft(self):
        """Verify that editing approved content clears approval and restores Draft status."""
        post = self.make_post(status="Approved", approved_by="Administrator", approved_on=now_datetime())
        previous = self.make_post(status="Approved", approved_by="Administrator", approved_on=post.approved_on)
        post.content = "Changed content"

        with patch.object(SocialMediaPost, "get_doc_before_save", return_value=previous):
            post.validate()

        self.assertEqual(post.status, "Draft")
        self.assertIsNone(post.approved_by)
        self.assertIsNone(post.approved_on)

    def test_changed_failed_publish_loses_approval(self):
        """Verify that editing a failed publish clears its previous approval."""
        post = self.make_post(
            status="Failed",
            generation_status="Ready",
            approved_by="Administrator",
            approved_on=now_datetime(),
            content="Changed content",
        )
        previous = self.make_post(
            status="Failed",
            generation_status="Ready",
            approved_by="Administrator",
            approved_on=post.approved_on,
        )

        with patch.object(SocialMediaPost, "get_doc_before_save", return_value=previous):
            post.validate()

        self.assertEqual(post.status, "Draft")
        self.assertIsNone(post.approved_by)

    def test_pending_content_cannot_be_changed(self):
        """Verify that content cannot change while approval is pending."""
        post = self.make_post(status="Pending Approval", content="Changed content")
        previous = self.make_post(status="Pending Approval")

        with patch.object(SocialMediaPost, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                post.validate()

    def test_workflow_change_cannot_hide_behind_content_change(self):
        """Verify that a content edit cannot bypass workflow transition controls."""
        post = self.make_post(
            status="Scheduled",
            post_on=add_to_date(now_datetime(), minutes=10),
            content="Changed content",
        )
        previous = self.make_post(status="Draft")

        with patch.object(SocialMediaPost, "get_doc_before_save", return_value=previous):
            with self.assertRaises(frappe.ValidationError):
                post.validate()

    def test_generation_must_be_ready_before_submission(self):
        """Verify that incomplete generated content cannot enter approval."""
        post = self.make_post(generation_status="Generating")
        with patch.object(SocialMediaPost, "check_permission"):
            with self.assertRaises(frappe.ValidationError):
                post.submit_for_approval()

    def test_rejection_requires_reason(self):
        """Verify that a manager must explain why a post was rejected."""
        post = self.make_post(status="Pending Approval")
        with patch.object(SocialMediaPost, "_require_manager"):
            with self.assertRaises(frappe.ValidationError):
                post.reject("  ")

    def test_schedule_requires_future_site_time(self):
        """Verify that an approved post can only be scheduled in the future."""
        post = self.make_post(status="Approved")
        past = add_to_date(now_datetime(), minutes=-1)
        with patch.object(SocialMediaPost, "_require_manager"):
            with self.assertRaises(frappe.ValidationError):
                post.schedule(str(past))

    def test_publish_claim_is_atomic(self):
        """Verify that publishing claims a post and commits the lock atomically."""
        post = self.make_post(name="POST-0001", status="Approved")
        with (
            patch.object(frappe.db, "sql", return_value=[frappe._dict(status="Approved", post_on=None)]),
            patch.object(SocialMediaPost, "reload"),
            patch.object(SocialMediaPost, "save"),
            patch.object(frappe.db, "commit") as commit,
        ):
            post._claim_for_publishing()

        self.assertEqual(post.status, "Publishing")
        commit.assert_called_once_with()

    def test_second_publish_claim_is_rejected(self):
        """Verify that concurrent workers cannot claim the same post twice."""
        post = self.make_post(name="POST-0001", status="Publishing")
        with patch.object(frappe.db, "sql", return_value=[frappe._dict(status="Publishing", post_on=None)]):
            with self.assertRaises(frappe.ValidationError):
                post._claim_for_publishing()
