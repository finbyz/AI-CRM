import praw
import frappe
from frappe import _
from frappe.utils import get_timestamp, now, add_to_date, get_datetime
from datetime import datetime, timedelta
import json
import requests
from typing import List, Dict, Any

class RedditAPI:
    def __init__(self, integration_name=None):
        """
        Initialize Reddit API with credentials from RedditIntegration doctype
        
        Args:
            integration_name: Name of the RedditIntegration document. 
                            If None, will use the first active integration found.
        """
        # Get Reddit Integration document
        if integration_name:
            self.integration = frappe.get_doc('Reddit Integration', integration_name)
        else:
            # Find the first connected Reddit Integration
            integrations = frappe.get_all(
                'Reddit Integration',
                filters={'connection_status': 'Connected'},
                limit=1
            )
            
            if not integrations:
                # Try to find any Reddit Integration
                integrations = frappe.get_all('Reddit Integration', limit=1)
                
            if not integrations:
                frappe.throw(_("No Reddit Integration found. Please create one first."))
                
            self.integration = frappe.get_doc('Reddit Integration', integrations[0].name)
        
        # Check if integration is connected
        if self.integration.connection_status != 'Connected':
            frappe.throw(_(f"Reddit Integration '{self.integration.name}' is not connected. Please connect it first."))
        
        # Get credentials from the integration
        client_id = self.integration.client_id
        client_secret = self.integration.get_password('client_secret')
        user_agent = self.integration.user_agent or 'ERPNext Reddit Monitor/1.0'
        username = self.integration.username
        
        # For PRAW, we need password authentication or OAuth
        # Since we have OAuth tokens, we'll use a different approach
        
        try:
            # Method 1: Use refresh token if available for script app
            if hasattr(self.integration, 'refresh_token') and self.integration.refresh_token:
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent,
                    refresh_token=self.integration.get_password('refresh_token')
                )
            else:
                # Method 2: Use read-only mode with client credentials
                self.reddit = praw.Reddit(
                    client_id=client_id,
                    client_secret=client_secret,
                    user_agent=user_agent
                )
                
        except Exception as e:
            frappe.throw(_(f"Failed to initialize Reddit API: {str(e)}"))
    
    def get_oauth_headers(self):
        """Get headers for direct Reddit API calls using OAuth token"""
        token = self.integration._get_valid_token()
        if not token:
            frappe.throw(_("No valid OAuth token available"))
            
        return {
            "Authorization": f"Bearer {token}",
            "User-Agent": self.integration.user_agent
        }
    
    def fetch_reddit_posts(self, subreddit_name: str, limit: int = 25) -> List[Dict[str, Any]]:
        """Fetch posts from a subreddit"""
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = []
            
            for submission in subreddit.new(limit=limit):
                # Determine post type
                post_type = "Text"
                if submission.url != submission.permalink:
                    if any(ext in submission.url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
                        post_type = "Image"
                    elif any(ext in submission.url.lower() for ext in ['.mp4', '.webm', '.gifv']):
                        post_type = "Video"
                    else:
                        post_type = "Link"
                
                post_data = {
                    'post_id': submission.id,
                    'title': submission.title[:140],  # Limit title length
                    'author': str(submission.author) if submission.author else '[deleted]',
                    'url': f"https://reddit.com{submission.permalink}",
                    'external_url': submission.url if submission.url != submission.permalink else '',
                    'post_type': post_type,
                    'score': submission.score,
                    'num_comments': submission.num_comments,
                    'selftext': submission.selftext,
                    'created_utc': datetime.fromtimestamp(submission.created_utc)
                }
                posts.append(post_data)
            
            return posts
            
        except Exception as e:
            frappe.log_error(f"Error fetching posts from r/{subreddit_name}: {str(e)}")
            raise
    
    def post_comment(self, post_id: str, comment_text: str) -> bool:
        """Post a comment on a Reddit post using OAuth API"""
        try:
            # Use the OAuth method from integration instead of PRAW
            result = self.integration.create_comment(post_id, comment_text)
            
            if result.get('status') == 'success':
                frappe.logger().info(f"Comment posted successfully on post {post_id}")
                return True
            else:
                frappe.log_error(f"Error posting comment on post {post_id}: {result.get('message')}")
                return False
                
        except Exception as e:
            frappe.log_error(f"Error posting comment on post {post_id}: {str(e)}")
            return False

def store_posts_in_db(subreddit_name: str, posts: List[Dict[str, Any]]) -> int:
    """Store fetched posts in Reddit Post doctype"""
    stored_count = 0
    
    for post_data in posts:
        # Check if post already exists
        if frappe.db.exists('Reddit Post', post_data['post_id']):
            continue
        
        try:
            # Create new Reddit Post record
            reddit_post = frappe.new_doc('Reddit Post')
            reddit_post.update({
                'subreddit': subreddit_name,
                'post_id': post_data['post_id'],
                'title': post_data['title'],
                'author': post_data['author'],
                'url': post_data['url'],
                'external_url': post_data['external_url'],
                'post_type': post_data['post_type'],
                'score': post_data['score'],
                'num_comments': post_data['num_comments'],
                'selftext': post_data['selftext'],
                'created_utc': post_data['created_utc'],
                'comment_status': 'Pending'
            })
            reddit_post.insert()
            stored_count += 1
            
        except Exception as e:
            frappe.log_error(f"Error storing post {post_data['post_id']}: {str(e)}")
    
    return stored_count

@frappe.whitelist()
def queue_ai_comment(post_name):
    """Queue AI comment for later processing"""
    try:
        post_doc = frappe.get_doc('Reddit Post', post_name)
        subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
        
        # Check delay requirement
        delay_minutes = subreddit_doc.comment_delay_minutes or 5
        comment_time = add_to_date(post_doc.created_utc, minutes=delay_minutes)
        current_time = get_datetime()
        
        if current_time >= comment_time:
            # Generate and post comment immediately
            return generate_ai_comment_internal(post_name, subreddit_doc.ai_comment_agent)
        else:
            # Schedule for later (will be picked up by scheduler)
            frappe.logger().info(f"Post {post_name} queued for AI comment after delay")
            return {'success': True, 'message': 'Queued for later processing'}
            
    except Exception as e:
        frappe.log_error(f"Error queuing AI comment for post {post_name}: {str(e)}")
        return {'success': False, 'error': str(e)}

def generate_ai_comment_internal(post_name, agent_name=None):
    """Internal function to generate AI comment without @frappe.whitelist()"""
    try:
        # Get Reddit Post
        post_doc = frappe.get_doc('Reddit Post', post_name)
        
        # Get subreddit document to check for AI agent
        subreddit_doc = None
        if frappe.db.exists('Subreddit', post_doc.subreddit):
            subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
            if not agent_name and subreddit_doc.ai_comment_agent:
                agent_name = subreddit_doc.ai_comment_agent
        
        if not agent_name:
            # Try to find Reddit Comment Generator agent
            agents = frappe.get_all(
                'AI Agent',
                filters={'name': ['like', '%reddit%comment%']},
                limit=1
            )
            if agents:
                agent_name = agents[0].name
            else:
                return {'success': False, 'error': 'No Reddit Comment AI Agent found'}
        
        # Prepare input for AI Agent
        agent_input = {
            "post_title": post_doc.title,
            "post_content": post_doc.selftext or "",
            "subreddit": post_doc.subreddit,
            "post_type": post_doc.post_type,
            "score": post_doc.score,
            "author": post_doc.author
        }
        
        # Call AI Agent
        ai_response = call_ai_agent_internal(agent_name, agent_input)
        
        if 'error' in ai_response:
            return {'success': False, 'error': ai_response['error']}
        
        # Extract comment from AI response
        comment_text = ai_response.get('comment', '')
        if not comment_text:
            return {'success': False, 'error': 'AI Agent returned empty comment'}
        
        # Post the AI-generated comment
        reddit_api = RedditAPI()
        success = reddit_api.post_comment(post_doc.post_id, comment_text)
        
        # Update post status
        if success:
            post_doc.comment_status = 'Commented'
            post_doc.comment_posted_at = frappe.utils.now()
            post_doc.comment_error = ''
            post_doc.ai_generated_comment = comment_text
            
            # Update subreddit AI comment count
            if subreddit_doc:
                subreddit_doc.ai_comments_generated = (subreddit_doc.ai_comments_generated or 0) + 1
                subreddit_doc.save()
        else:
            post_doc.comment_status = 'Failed'
            post_doc.comment_error = 'Failed to post AI generated comment'
        
        post_doc.save()
        return {'success': success, 'comment': comment_text}
        
    except Exception as e:
        frappe.log_error(f"Error generating AI comment for post {post_name}: {str(e)}")
        return {'success': False, 'error': str(e)}

def call_ai_agent_internal(agent_name: str, input_data: dict) -> dict:
    """Internal AI Agent call without @frappe.whitelist()"""
    try:
        # Get AI Agent document
        if not frappe.db.exists('AI Agent', agent_name):
            return {"error": f"AI Agent '{agent_name}' not found"}
            
        agent = frappe.get_doc('AI Agent', agent_name)
        
        # Prepare the prompt with input data
        system_messages = frappe.get_all(
            'AI Agent Message',
            filters={'parent': agent_name, 'message_type': 'system'},
            fields=['content'],
            order_by='idx'
        )
        
        human_messages = frappe.get_all(
            'AI Agent Message',
            filters={'parent': agent_name, 'message_type': 'human'},
            fields=['content'],
            order_by='idx'
        )
        
        # Build messages array
        messages = []
        
        # Add system messages
        for msg in system_messages:
            messages.append({
                "role": "system",
                "content": msg.content
            })
        
        # Add human messages with variable substitution
        for msg in human_messages:
            content = msg.content
            # Replace variables in the message
            for key, value in input_data.items():
                content = content.replace(f"{{{key}}}", str(value))
            
            messages.append({
                "role": "user",
                "content": content
            })
        
        # Call the LLM API
        from frappe.integrations.utils import make_post_request
        
        # Get OpenAI settings
        try:
            openai_settings = frappe.get_single('OpenAI Settings')
            if not openai_settings.api_key:
                return {"error": "OpenAI API key not configured"}
        except:
            return {"error": "OpenAI Settings not found"}
        
        headers = {
            "Authorization": f"Bearer {openai_settings.get_password('api_key')}",
            "Content-Type": "application/json"
        }
        
        # Prepare request data
        request_data = {
            "model": agent.llm or "gpt-4o-mini",
            "messages": messages,
            "temperature": agent.temperature or 0.7,
            "max_tokens": agent.max_tokens or 150
        }
        
        # Add response format if structured output is defined
        if agent.structured_output:
            try:
                response_format = json.loads(agent.structured_output)
                request_data["response_format"] = {
                    "type": "json_schema",
                    "json_schema": response_format
                }
            except json.JSONDecodeError:
                frappe.log_error("Invalid structured output JSON in AI Agent")
        
        # Make API call
        response = make_post_request(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            data=json.dumps(request_data)
        )
        
        if response.get('choices'):
            content = response['choices'][0]['message']['content']
            
            # Try to parse as JSON if structured output is expected
            if agent.structured_output:
                try:
                    return json.loads(content)
                except json.JSONDecodeError:
                    return {"comment": content}
            else:
                return {"comment": content}
        else:
            return {"error": "No response from AI Agent"}
            
    except Exception as e:
        frappe.log_error(f"Error calling AI Agent {agent_name}: {str(e)}")
        return {"error": str(e)}

# Public API Functions with @frappe.whitelist()

@frappe.whitelist()
def generate_ai_comment(post_name, agent_name=None):
    """Public API to generate AI comment"""
    return generate_ai_comment_internal(post_name, agent_name)

@frappe.whitelist()
def call_ai_agent(agent_name: str, input_data: dict) -> dict:
    """Public API to call AI Agent"""
    return call_ai_agent_internal(agent_name, input_data)

@frappe.whitelist()
def fetch_posts_manually(subreddit_name, integration_name=None):
    """Manually fetch posts for a subreddit using RedditIntegration credentials"""
    try:
        reddit_api = RedditAPI(integration_name)
        posts = reddit_api.fetch_reddit_posts(subreddit_name)
        stored_count = store_posts_in_db(subreddit_name, posts)
        
        # Update subreddit stats if Subreddit doctype exists
        if frappe.db.exists('Subreddit', subreddit_name):
            subreddit_doc = frappe.get_doc('Subreddit', subreddit_name)
            subreddit_doc.last_monitored = frappe.utils.now()
            subreddit_doc.posts_fetched_today = (subreddit_doc.posts_fetched_today or 0) + stored_count
            subreddit_doc.total_posts_monitored = (subreddit_doc.total_posts_monitored or 0) + stored_count
            subreddit_doc.last_error = ''
            subreddit_doc.save()
        
        return {'count': stored_count}
    except Exception as e:
        frappe.throw(str(e))

@frappe.whitelist()
def post_comment_manually(post_name, integration_name=None, use_ai=False):
    """Manually post comment on a specific post using RedditIntegration"""
    try:
        if use_ai:
            return generate_ai_comment(post_name)
        
        reddit_api = RedditAPI(integration_name)
        post_doc = frappe.get_doc('Reddit Post', post_name)
        
        # Get comment template from Subreddit if it exists
        comment_template = "Thanks for sharing!"  # Default comment
        if frappe.db.exists('Subreddit', post_doc.subreddit):
            subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
            if subreddit_doc.comment_template:
                comment_template = subreddit_doc.comment_template
        
        success = reddit_api.post_comment(post_doc.post_id, comment_template)
        
        if success:
            post_doc.comment_status = 'Commented'
            post_doc.comment_posted_at = frappe.utils.now()
            post_doc.comment_error = ''
        else:
            post_doc.comment_status = 'Failed'
            post_doc.comment_error = 'Manual comment failed'
        
        post_doc.save()
        return {'success': success}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_post_statistics(subreddit_name):
    """Get statistics for posts in a subreddit"""
    try:
        stats = frappe.db.sql("""
            SELECT 
                COUNT(*) as total_posts,
                COUNT(CASE WHEN DATE(creation) = CURDATE() THEN 1 END) as posts_today,
                COUNT(CASE WHEN comment_status = 'Commented' THEN 1 END) as commented,
                COUNT(CASE WHEN comment_status = 'Pending' THEN 1 END) as pending,
                COUNT(CASE WHEN comment_status = 'Failed' THEN 1 END) as failed,
                ROUND(AVG(score), 1) as avg_score,
                COUNT(CASE WHEN ai_generated_comment IS NOT NULL THEN 1 END) as ai_commented
            FROM `tabReddit Post`
            WHERE subreddit = %s
        """, subreddit_name, as_dict=True)[0]
        
        return stats
        
    except Exception as e:
        frappe.throw(str(e))

@frappe.whitelist()
def get_available_integrations():
    """Get list of available Reddit integrations"""
    try:
        integrations = frappe.get_all(
            'Reddit Integration',
            fields=['name', 'username', 'connection_status', 'connected_at'],
            order_by='connection_status desc, connected_at desc'
        )
        return integrations
    except Exception as e:
        frappe.throw(str(e))

@frappe.whitelist()
def get_available_ai_agents():
    """Get list of available AI Agents for Reddit commenting"""
    try:
        agents = frappe.get_all(
            'AI Agent',
            fields=['name', 'agent_name', 'llm'],
            order_by='name'
        )
        return agents
    except Exception as e:
        frappe.throw(str(e))

@frappe.whitelist()
def test_ai_agent_connection(agent_name):
    """Test AI Agent connection and configuration"""
    try:
        # Test with sample data
        test_input = {
            "post_title": "Test Post Title",
            "post_content": "This is a test post content",
            "subreddit": "test",
            "post_type": "Text",
            "score": 10,
            "author": "testuser"
        }
        
        result = call_ai_agent_internal(agent_name, test_input)
        
        if 'error' in result:
            return {'success': False, 'error': result['error']}
        else:
            return {'success': True, 'response': result}
            
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def bulk_update_comment_status(post_names, new_status):
    """Bulk update comment status for multiple posts"""
    try:
        if not isinstance(post_names, list):
            post_names = json.loads(post_names)
        
        updated_count = 0
        for post_name in post_names:
            try:
                post_doc = frappe.get_doc('Reddit Post', post_name)
                post_doc.comment_status = new_status
                post_doc.save()
                updated_count += 1
            except Exception as e:
                frappe.log_error(f"Error updating post {post_name}: {str(e)}")
        
        return {'success': True, 'updated_count': updated_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_reddit_post_details(post_name):
    """Get detailed information about a Reddit post"""
    try:
        post_doc = frappe.get_doc('Reddit Post', post_name)
        subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
        
        return {
            'post': post_doc.as_dict(),
            'subreddit': subreddit_doc.as_dict()
        }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def retry_failed_comments(subreddit_name=None, limit=10):
    """Retry failed comments for a specific subreddit or all subreddits"""
    try:
        filters = {'comment_status': 'Failed'}
        if subreddit_name:
            filters['subreddit'] = subreddit_name
        
        failed_posts = frappe.get_all(
            'Reddit Post',
            filters=filters,
            fields=['name', 'post_id', 'subreddit'],
            limit=limit
        )
        
        retry_count = 0
        for post in failed_posts:
            try:
                # Reset status to Pending for retry
                post_doc = frappe.get_doc('Reddit Post', post.name)
                post_doc.comment_status = 'Pending'
                post_doc.comment_error = ''
                post_doc.save()
                retry_count += 1
            except Exception as e:
                frappe.log_error(f"Error retrying post {post.name}: {str(e)}")
        
        return {'success': True, 'retry_count': retry_count}
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Background job functions (not whitelisted)

def process_ai_comment_queue():
    """Process queued AI comments (called by scheduler)"""
    try:
        # This is called by the scheduler task process_pending_ai_comments
        # Implementation is in scheduler_tasks.py
        pass
    except Exception as e:
        frappe.log_error(f"Error processing AI comment queue: {str(e)}")

def cleanup_failed_posts():
    """Clean up posts that have been failing for too long"""
    try:
        # Posts that have been failing for more than 7 days
        cutoff_date = add_to_date(get_datetime(), days=-7)
        
        old_failed_posts = frappe.get_all(
            'Reddit Post',
            filters={
                'comment_status': 'Failed',
                'modified': ['<', cutoff_date]
            },
            fields=['name']
        )
        
        for post in old_failed_posts:
            try:
                post_doc = frappe.get_doc('Reddit Post', post.name)
                post_doc.comment_status = 'Skipped'
                post_doc.comment_error = 'Skipped after multiple failures'
                post_doc.save()
            except Exception as e:
                frappe.log_error(f"Error updating failed post {post.name}: {str(e)}")
                
    except Exception as e:
        frappe.log_error(f"Error cleaning up failed posts: {str(e)}")