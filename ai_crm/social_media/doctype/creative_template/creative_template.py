# Copyright (c) 2026, finbyz and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CreativeTemplate(Document):
    def validate(self):
        if self.format == "Carousel":
            if not 2 <= (self.min_slides or 0) <= (self.max_slides or 0) <= 12:
                frappe.throw(_("Slides must satisfy 2 <= Min Slides <= Max Slides <= 12"))
        if self.example_json:
            try:
                frappe.parse_json(self.example_json)
            except Exception:
                frappe.throw(_("Example Output must be valid JSON"))
