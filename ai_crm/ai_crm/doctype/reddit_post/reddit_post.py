
import frappe
from frappe.model.document import Document

class RedditPost(Document):
    def validate(self):
        if self.title and len(self.title) > 140:
            self.title = self.title[:137] + "..."
    def after_insert(self):
        """Trigger AI comment generation after post is inserted"""
        if self.comment_status == "Pending":
            try:
                subreddit_doc = frappe.get_doc("Subreddit", self.subreddit)
                if (subreddit_doc.auto_comment_enabled and 
                subreddit_doc.use_ai_comments and 
                subreddit_doc.ai_comment_agent):
                    
                    frappe.enqueue('ai_crm.reddit_api.generate_ai_comment',post_name=self.name)
                    frappe.logger().info(f"Queued AI comment for Reddit post: {self.name}")
                    
            except Exception as e:
                frappe.log_error(f"Error queuing AI comment for post {self.name}: {str(e)}")
   
    def get_reddit_url(self):
        """Get the proper Reddit URL for this post"""
        if self.url and self.url.startswith('https://www.reddit.com'):
            return self.url
        elif self.post_id and self.subreddit:
            return f"https://www.reddit.com/r/{self.subreddit}/comments/{self.post_id}/"
        else:
            return f"https://www.reddit.com/r/{self.subreddit}/"

    
    
    

    