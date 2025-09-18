# reddit_post.py
import frappe
from frappe.model.document import Document

class RedditPost(Document):
    def validate(self):
        # Truncate title if too long
        if self.title and len(self.title) > 140:
            self.title = self.title[:137] + "..."
    
    def after_insert(self):
        """Trigger AI comment generation after post is inserted"""
        if self.comment_status == "Pending":
            # Check if subreddit has AI commenting enabled
            subreddit_doc = frappe.get_doc("Subreddit", self.subreddit)
            if subreddit_doc.auto_comment and subreddit_doc.use_ai_comments and subreddit_doc.ai_comment_agent:
                # Queue for AI comment generation (will be processed by scheduler)
                frappe.enqueue(
                    'ai_crm.reddit_api.queue_ai_comment',
                    post_name=self.name,
                    queue='short',
                    timeout=300
                )