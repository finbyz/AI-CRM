import frappe
from frappe.model.document import Document

class RedditPost(Document):
    def validate(self):
        # Truncate title if too long
        if self.title and len(self.title) > 140:
            self.title = self.title[:137] + "..."