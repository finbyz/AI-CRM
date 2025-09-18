import frappe
from frappe.model.document import Document

class Subreddit(Document):
    def validate(self):
        # Remove 'r/' prefix if present
        if self.subreddit_name and self.subreddit_name.startswith('r/'):
            self.subreddit_name = self.subreddit_name[2:]
        
        # Validate subreddit name format
        if not self.subreddit_name.replace('_', '').replace('-', '').isalnum():
            frappe.throw("Invalid subreddit name format")
    
    def on_update(self):
        # Reset error when settings are updated
        if self.has_value_changed('comment_template') or self.has_value_changed('auto_comment'):
            self.last_error = ''