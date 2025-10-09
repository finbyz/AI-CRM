
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
    
    @frappe.whitelist()
    def fetch_Reddit_post_comments(self, limit=10):
        """Fetch comments using public API"""
        try:
            import requests
            from datetime import datetime
            
            frappe.logger().info(f"Fetching comments for post {self.post_id}")
            
            comments_url = f"https://www.reddit.com/comments/{self.post_id}.json"
            headers = {"User-Agent": "Mozilla/5.0 (compatible; RedditBot/1.0)"}
            
            response = requests.get(comments_url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            comments = []
            if len(data) > 1 and 'data' in data[1]:
                comment_list = data[1]['data'].get('children', [])
                
                for comment_data in comment_list[:limit]:
                    if comment_data.get('kind') != 't1':
                        continue
                        
                    comment = comment_data.get('data', {})
                    body = comment.get('body', '')
                    author = comment.get('author', '[deleted]')
                    
                    if body in ['[deleted]', '[removed]', ''] or author in ['[deleted]', None]:
                        continue
                    
                    comments.append({
                        'author': author,
                        'body': body,
                        'score': comment.get('score', 0)
                    })
            
            frappe.logger().info(f"Fetched {len(comments)} valid comments")
            
            if comments:
                self.set('reddit_post_comments', [])
                
                for comment in comments:
                    # Map to existing child table fields
                    self.append('reddit_post_comments', {
                        'author': comment['author'],    
                        'content': comment['body'],       
                        'score': comment['score']         
                    })
                    
                    frappe.logger().info(f"Added: {comment['author']} - {comment['body'][:50]}")
                
                self.save(ignore_permissions=True)
                frappe.db.commit()
                
                return {
                    'success': True,
                    'message': f'Fetched {len(comments)} comments',
                    'comments_count': len(comments)
                }
            else:
                return {
                    'success': False,
                    'message': 'No comments found'
                }
        except Exception as e:
            import traceback
            error_msg = f"Error: {str(e)}\n{traceback.format_exc()}"
            frappe.logger().error(error_msg)
            return {
                'success': False,
                'error': str(e)
            }
   
    def get_reddit_url(self):
        """Get the proper Reddit URL for this post"""
        if self.url and self.url.startswith('https://www.reddit.com'):
            return self.url
        elif self.post_id and self.subreddit:
            return f"https://www.reddit.com/r/{self.subreddit}/comments/{self.post_id}/"
        else:
            return f"https://www.reddit.com/r/{self.subreddit}/"

    
    
    

    