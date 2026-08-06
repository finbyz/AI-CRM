# Copyright (c) 2025, Finbyz Tech Pvt Ltd and Contributors
# See license.txt

import frappe
from frappe.tests.utils import FrappeTestCase


class TestContentHubIdea(FrappeTestCase):
    def test_idea_is_a_minimal_content_hub_child_row(self):
        """Verify that an idea contains only the title and optional description."""
        meta = frappe.get_meta("Content Hub Idea")
        data_fields = [field.fieldname for field in meta.fields if not field.fieldtype.endswith("Break")]

        self.assertEqual(meta.istable, 1)
        self.assertEqual(data_fields, ["idea_title", "description"])
        self.assertEqual(meta.get_field("idea_title").reqd, 1)
        self.assertEqual(meta.get_field("description").fieldtype, "Small Text")
