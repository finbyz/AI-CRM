
import frappe
from frappe.model.document import Document
class Subreddit(Document):
    def validate(self):
        
        if self.subreddit_name and self.subreddit_name.startswith('r/'):
            self.subreddit_name = self.subreddit_name[2:]
        if self.reddit_integration:
            if not frappe.db.exists('Reddit Integration', self.reddit_integration):
                frappe.throw(f"Reddit Integration '{self.reddit_integration}' does not exist")
            
            integration = frappe.get_doc('Reddit Integration', self.reddit_integration)
            if integration.connection_status != 'Connected':
                frappe.msgprint(
                    f"Warning: Reddit Integration '{self.reddit_integration}' is not connected.",
                    indicator='orange'
                )
        
        if not self.subreddit_name.replace('_', '').replace('-', '').isalnum():
            frappe.throw("Invalid subreddit name format")
    def on_update(self):
        
        if (self.has_value_changed('comment_template') or 
            self.has_value_changed('auto_comment_enabled') or 
            self.has_value_changed('reddit_integration')):
            self.last_error = ''
    
    def get_reddit_integration(self):
        """Get the Reddit Integration to use for this subreddit"""
        if self.reddit_integration:
            return self.reddit_integration
        
        integrations = frappe.get_all(
            'Reddit Integration',
            filters={'connection_status': 'Connected'},
            limit=1
        )
        
        if integrations:
            return integrations[0].name
        
        frappe.throw("No Reddit Integration configured")