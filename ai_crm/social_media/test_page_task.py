"""Regression tests for source-page access during developer assignment."""

from unittest import TestCase
from unittest.mock import Mock, patch

from ai_crm.social_media import page_task


class TestDeveloperPageAccess(TestCase):
    def setUp(self):
        self.page = Mock(doctype="NextJS Page", name="source-page")
        self.page.name = "source-page"
        self.user = "developer@example.com"
        self.frappe_patch = patch.object(page_task, "frappe")
        self.frappe = self.frappe_patch.start()
        self.addCleanup(self.frappe_patch.stop)
        self.translation_patch = patch.object(page_task, "_", lambda message: message)
        self.translation_patch.start()
        self.addCleanup(self.translation_patch.stop)
        self.frappe.has_permission.return_value = False
        self.frappe.get_system_settings.return_value = False
        self.frappe.PermissionError = PermissionError
        self.frappe.throw.side_effect = lambda message, error: self.raise_error(message, error)

    @staticmethod
    def raise_error(message, error):
        raise error(message)

    def test_existing_access_does_not_change_shares(self):
        self.frappe.has_permission.return_value = True
        self.frappe.get_system_settings.return_value = True

        page_task.ensure_developer_page_access(self.page, self.user)

        self.frappe.has_permission.assert_called_once_with(doc=self.page, ptype="read", user=self.user)
        self.frappe.share.add.assert_not_called()
        self.page.has_permission.assert_not_called()

    def test_missing_access_grants_read_only_share(self):
        page_task.ensure_developer_page_access(self.page, self.user)

        self.page.has_permission.assert_called_once_with("share")
        self.frappe.share.add.assert_called_once_with(
            "NextJS Page", "source-page", user=self.user, read=1
        )

    def test_disabled_sharing_rejects_assignment(self):
        self.frappe.get_system_settings.return_value = True

        with self.assertRaisesRegex(PermissionError, "document sharing is disabled"):
            page_task.ensure_developer_page_access(self.page, self.user)

        self.frappe.share.add.assert_not_called()

    def test_assigner_without_share_permission_is_rejected(self):
        self.page.has_permission.return_value = False

        with self.assertRaisesRegex(PermissionError, "permission to share this page"):
            page_task.ensure_developer_page_access(self.page, self.user)

        self.frappe.share.add.assert_not_called()

    def test_access_failure_stops_before_task_creation(self):
        employee = Mock(status="Active", user_id=self.user)
        self.frappe.get_doc.side_effect = [self.page, employee]
        self.frappe.get_system_settings.return_value = True

        with patch.object(page_task, "assign_to") as assign_to:
            with self.assertRaises(PermissionError):
                page_task.create_page_task("source-page", "EMP-1", "Build this page")

        self.assertEqual(self.frappe.get_doc.call_count, 2)
        assign_to.assert_not_called()
