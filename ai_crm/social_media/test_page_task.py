"""Regression tests for developer assignment: source-page access, project and task type."""

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
        self.frappe.ValidationError = ValueError
        self.frappe.throw.side_effect = self.raise_error

    @staticmethod
    def raise_error(message, error=ValueError):
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
                page_task.create_page_task("source-page", "EMP-1", "Build this page", "PROJ-0001")

        self.assertEqual(self.frappe.get_doc.call_count, 2)
        assign_to.assert_not_called()


class TestPageTaskFields(TestCase):
    """The Task carries the project and task type chosen in the dialog."""

    def setUp(self):
        self.page = Mock(doctype="NextJS Page", title="Inventory Automation Guide")
        self.page.name = "inventory-automation-guide"
        self.employee = Mock(status="Active", user_id="developer@example.com")
        self.frappe_patch = patch.object(page_task, "frappe")
        self.frappe = self.frappe_patch.start()
        self.addCleanup(self.frappe_patch.stop)
        self.translation_patch = patch.object(page_task, "_", lambda message: message)
        self.translation_patch.start()
        self.addCleanup(self.translation_patch.stop)
        # The developer can already read the page, and the ToDo already exists, so no share or assign.
        self.frappe.has_permission.return_value = True
        self.frappe.db.exists.return_value = True
        self.frappe.ValidationError = ValueError
        self.frappe.throw.side_effect = TestDeveloperPageAccess.raise_error
        self.task = Mock()
        self.frappe.get_doc.side_effect = [self.page, self.employee, self.task]

    def create(self, **kwargs):
        args = {
            "page_name": self.page.name,
            "employee": "EMP-1",
            "description": "Build this page",
            "project": "PROJ-0001",
            "exp_start_date": "2026-10-29",
            "exp_end_date": "2026-10-30",
        }
        args.update(kwargs)
        with patch.object(page_task, "assign_to"):
            return page_task.create_page_task(**args)

    def task_values(self):
        return self.frappe.get_doc.call_args_list[2].args[0]

    def test_project_and_task_type_reach_the_task(self):
        self.create(task_type="Bug Fix")

        values = self.task_values()
        self.assertEqual(values["project"], "PROJ-0001")
        self.assertEqual(values["type"], "Bug Fix")

    def test_task_type_defaults_to_development(self):
        self.create()

        self.assertEqual(self.task_values()["type"], page_task.DEFAULT_TASK_TYPE)
        self.assertEqual(self.task_values()["type"], "Development")

    def test_blank_project_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Select a Project"):
            self.create(project="  ")

        self.task.insert.assert_not_called()

    def test_unknown_project_is_rejected(self):
        self.frappe.db.exists.side_effect = lambda doctype, name: doctype != "Project"

        with self.assertRaisesRegex(ValueError, "does not exist"):
            self.create()

        self.task.insert.assert_not_called()

    def test_unknown_task_type_is_rejected(self):
        self.frappe.db.exists.side_effect = lambda doctype, name: doctype != "Task Type"

        with self.assertRaisesRegex(ValueError, "Task Type"):
            self.create(task_type="Nonexistent")

        self.task.insert.assert_not_called()
