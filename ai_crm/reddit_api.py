
import frappe
from frappe import _
from frappe.utils import get_timestamp, now, add_to_date, get_datetime
from datetime import datetime, timedelta
import json
import requests
from typing import List, Dict, Any
import traceback
from bs4 import BeautifulSoup
import re

class RedditAPI:
    def __init__(self, integration_name=None):
        try:
            if not integration_name:
                integrations = frappe.get_all(
                    'Reddit Integration',
                    filters={'connection_status': 'Connected'},
                    limit=1
                )
                if not integrations:
                    frappe.throw(_("No connected Reddit Integration found"))
                integration_name = integrations[0].name
            
            self.integration = frappe.get_doc('Reddit Integration', integration_name)
            if not self.integration.ensure_valid_token():
                frappe.throw(
                    _(f"Failed to validate/refresh access token for {integration_name}. "
                      "Please reconnect your Reddit account.")
                )
            self.integration.reload()
            self.access_token = self.integration.get_password("access_token")
            if not self.access_token:
                frappe.throw(
                    _(f"No access token available for {integration_name}. "
                      "Please reconnect your Reddit account.")
                )
            self.user_agent = self.integration.get_user_agent()
            
            frappe.logger().info(
                f"RedditAPI initialized for u/{self.integration.username} "
                f"(integration: {integration_name})"
            )
        except Exception as e:
            frappe.log_error(
                title=f"Reddit API Initialization Failed - {integration_name}",
                message=frappe.get_traceback()
            )
            raise
    def _get_headers(self):
        """Get headers with fresh access token"""
        if not self.integration.ensure_valid_token():
            frappe.throw(_("Reddit authentication failed. Token refresh unsuccessful."))
        
        self.integration.reload()
        self.access_token = self.integration.get_password("access_token")
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "User-Agent": self.user_agent
        }
    
    def scrape_external_content(self, url):
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (compatible; Reddit Bot)'
            })
            soup = BeautifulSoup(response.content, 'html.parser')
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text[:2000]
        except Exception as e:  # FIX: Added Exception as e
            frappe.logger().error(f"Error scraping {url}: {str(e)}")
            return None
            
    def fetch_reddit_posts(self, subreddit: str, sort_type: str = "hot", limit: int = 5, time_filter: str = "week") -> List[Dict]:
        valid_sorts = ["hot", "new", "top", "rising","best"]
        if sort_type not in valid_sorts:
            frappe.log_error(f"Invalid sort_type: {sort_type}. Valid options: {valid_sorts}")
            return []
        
        if sort_type in ["hot", "new", "top", "rising", "best"]:
            base_url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json"
            params = {"limit": limit * 2, "t": time_filter}
        else:
            base_url = f"https://www.reddit.com/r/{subreddit}/{sort_type}.json"
            params = {"limit": limit * 2}
        
        headers = {
            "User-Agent": self.integration.get_user_agent()
        }
        try:
            frappe.logger().info(f"Fetching {sort_type} posts from r/{subreddit} with limit {limit}")
            
            response = requests.get(base_url, headers=headers, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            posts = []
            existing_post_ids = set(frappe.get_all(
                'Reddit Post',
                filters={'subreddit': subreddit},
                pluck='post_id'
            ))
            for child in data.get("data", {}).get("children", []):
                post_data = child.get("data", {})
                post_id = post_data.get('id', '')
                
                if post_id in existing_post_ids:
                    frappe.logger().info(f"Skipping duplicate post: {post_id}")
                    continue
                
                if post_data.get('stickied', False):
                    frappe.logger().info(f"Skipping stickied post: {post_id}")
                    continue
                
                if len(posts) >= limit:
                    break
                    
                post_content = self._get_reddit_post_content(post_data)
                post_type = self._determine_post_type(post_data)
                
                permalink = post_data.get('permalink', '')
                reddit_url = f"https://www.reddit.com{permalink}" if permalink else f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/"
                
                original_url = post_data.get("url", "")
                is_external_link = (
                    original_url and 
                    not any(domain in original_url.lower() for domain in ['reddit.com', 'redd.it']) and
                    original_url != reddit_url
                )
                external_url = original_url if is_external_link else ""
                post_obj = {
                    "id": post_id,
                    "title": post_data.get("title", ""),
                    "author": post_data.get("author", ""),
                    "score": post_data.get("score", 0),
                    "url": reddit_url,  
                    "external_url": external_url,  
                    "original_url": original_url,
                    "permalink": permalink,
                    "created_utc": post_data.get("created_utc", 0),
                    "num_comments": post_data.get("num_comments", 0),
                    "selftext": post_content,
                    "post_type": post_type,
                    "sort_type": sort_type,
                    "time_filter": time_filter if sort_type in ["top", "controversial"] else None,
                    
                }
                
                posts.append(post_obj)
                frappe.logger().info(f"NEW POST: {post_obj['title'][:50]}... | ID: {post_id} | Comments: {post_obj['num_comments']}")
            
            frappe.logger().info(f"Successfully fetched {len(posts)} NEW posts from r/{subreddit} ({sort_type})")
            return posts

        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error fetching {sort_type} posts from r/{subreddit}: {str(e)}"
            if hasattr(e, 'response') and e.response is not None:
                error_msg += f" | Status: {e.response.status_code} | Response: {e.response.text[:200]}"
            frappe.log_error(error_msg)
            return []
        except Exception as e:
            frappe.log_error(f"Unexpected error fetching {sort_type} posts from r/{subreddit}: {str(e)}\n{traceback.format_exc()}")
            return []

    def _get_reddit_post_content(self, post_data):
        """Get post content"""
        selftext = post_data.get('selftext', '').strip()
        if selftext and selftext not in ['', '[removed]', '[deleted]']:
            return selftext[:2000]
        
        url = post_data.get('url', '')
        if url and not any(domain in url.lower() for domain in ['reddit.com', 'redd.it']):
            try:
                scraped = self.scrape_external_content(url)
                if scraped:
                    return scraped
            except:
                pass
            return f"External link: {url}"
        
        return post_data.get('title', '')
    
    def create_comment(self, post_id, comment_text):
        try:
            if not post_id or not comment_text:
                return False
            
            if not self.integration.ensure_valid_token():
                return False
            
            self.integration.reload()
            self.access_token = self.integration.get_password("access_token")
            
            url = "https://oauth.reddit.com/api/comment"
            data = {
                "thing_id": f"t3_{post_id}",
                "text": comment_text.strip()
            }
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": self.user_agent
            }
            
            response = requests.post(url, headers=headers, data=data, timeout=30)
            
            if response.status_code == 200:
                return True
            
            frappe.log_error(
                f"Reddit comment failed: {response.status_code} - {response.text[:200]}",
                "Reddit Comment Error"
            )
            return False
            
        except Exception as e:
            frappe.log_error(str(e), "Reddit Comment Exception")
            return False
    def fetch_post_comments(self, post_id, limit=10, sort='top'):
        """Fetch comments for a post with enhanced debugging"""
        try:
            comments_url = f"https://oauth.reddit.com/comments/{post_id}"
            params = {
                'sort': sort,
                'limit': limit,
                'depth': 1
            }
            
            if not self.integration.ensure_valid_token():
                frappe.log_error(
                    title=f"Token Validation Failed - {post_id}",
                    message="Failed to validate/refresh Reddit access token"
                )
                frappe.throw(_("Failed to validate token"))
            
            self.integration.reload()
            self.access_token = self.integration.get_password("access_token")
            
            if not self.access_token:
                frappe.log_error(
                    title=f"No Access Token - {post_id}",
                    message=f"No access token available for integration: {self.integration.name}"
                )
                frappe.throw(_("No access token available"))
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "User-Agent": self.user_agent
            }
            
            frappe.logger().info(
                f" Fetching {sort} comments for post: {post_id} (limit: {limit})"
            )
            
            # Make API call
            response = requests.get(comments_url, headers=headers, params=params, timeout=10)
            
            # Log response status
            frappe.logger().info(f"Reddit API Response Status: {response.status_code}")
            
            if response.status_code != 200:
                frappe.log_error(
                    title=f"Reddit API Error - {post_id}",
                    message=f"Status: {response.status_code}\nResponse: {response.text[:500]}"
                )
                response.raise_for_status()
            
            data = response.json()
            comments = []
            
            # Parse comments
            if len(data) > 1:
                comment_list = data[1]['data']['children']
                frappe.logger().info(f"Found {len(comment_list)} comment objects in response")
                
                for comment_data in comment_list:
                    if comment_data.get('kind') != 't1':
                        continue
                    
                    comment = comment_data['data']
                    
                    # Skip deleted/removed comments
                    if (comment.get('body') in ['[deleted]', '[removed]'] or 
                        comment.get('body') is None or
                        comment.get('author') is None):
                        continue
                    
                    comments.append({
                        'author': comment.get('author', '[deleted]'),
                        'body': comment.get('body', ''),
                        'score': comment.get('score', 0),
                        'created_utc': comment.get('created_utc', 0),
                        'comment_id': comment.get('id', '')
                    })
                    
                    if len(comments) >= limit:
                        break
            
            frappe.logger().info(f"Successfully fetched {len(comments)} valid {sort} comments")
            
            if len(comments) == 0:
                frappe.logger().warning(
                    f" No valid comments found for post {post_id}. "
                    "All comments might be deleted/removed."
                )
            
            return comments
            
        except requests.exceptions.HTTPError as e:
            error_msg = f"HTTP Error fetching comments for {post_id}: {str(e)}"
            frappe.logger().error(f"{error_msg}")
            frappe.log_error(
                title=f"Comment Fetch HTTP Error - {post_id}",
                message=f"{error_msg}\nResponse: {e.response.text if e.response else 'No response'}"
            )
            return []
            
        except Exception as e:
            error_msg = f"Error fetching comments for {post_id}: {str(e)}"
            frappe.logger().error(f"{error_msg}")
            frappe.log_error(
                title=f"Comment Fetch Error - {post_id}",
                message=f"{error_msg}\n{traceback.format_exc()}"
            )
        return []
        
    def _determine_post_type(self, post_data):
        url = post_data.get('url', '')
        selftext = post_data.get('selftext', '')
        post_hint = post_data.get('post_hint', '')
        
        if selftext and selftext.strip() and selftext not in ['', '[removed]', '[deleted]']:
            return "Text"
        
        if post_hint:
            if 'image' in post_hint:
                return "Image"
            elif 'video' in post_hint:
                return "Video"
            elif 'link' in post_hint:
                return "Link"
        if url:
            if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
                return "Image"
            elif any(ext in url.lower() for ext in ['.mp4', '.webm', '.gifv', 'youtube.com', 'youtu.be']):
                return "Video"
            elif any(domain in url.lower() for domain in ['reddit.com', 'redd.it']):
                return "Text"  
            else:
                return "Link"
        return "Text"
 
def store_posts_in_db(subreddit_name: str, posts: List[Dict[str, Any]]) -> int:
    """Store posts in database and fetch comments with enhanced logging"""
    from datetime import datetime
    stored_count = 0
    
    # Get integration_name once for all posts
    integration_name = None
    subreddit_doc = None
    
    if frappe.db.exists('Subreddit', subreddit_name):
        subreddit_doc = frappe.get_doc('Subreddit', subreddit_name)
        integration_name = subreddit_doc.reddit_integration
        
        if not integration_name:
            frappe.logger().warning(
                f"No Reddit Integration configured for r/{subreddit_name}. "
                "Comments will NOT be fetched automatically."
            )
        else:
            frappe.logger().info(f"Using Reddit Integration: {integration_name}")
    
    for post_data in posts:
        post_id = post_data.get('post_id') or post_data.get('id')
        
        if frappe.db.exists('Reddit Post', post_id):
            frappe.logger().debug(f"Skipping duplicate post: {post_id}")
            continue
        
        try:
            created_utc = post_data.get('created_utc')
            if created_utc:
                created_datetime = datetime.fromtimestamp(created_utc)
            else:
                created_datetime = frappe.utils.now_datetime()
            
            # Create new Reddit Post
            reddit_post = frappe.new_doc('Reddit Post')
            reddit_post.update({
                'subreddit': subreddit_name,
                'post_id': post_id,
                'title': post_data.get('title', ''),
                'author': post_data.get('author', ''),
                'url': post_data.get('url', ''),
                'external_url': post_data.get('external_url', ''),
                'post_type': post_data.get('post_type', 'Text'),
                'score': post_data.get('score', 0),
                'num_comments': post_data.get('num_comments', 0),
                'selftext': post_data.get('selftext', ''),
                'created_utc': created_datetime,
                'comment_status': 'Pending',
            })
            reddit_post.insert(ignore_permissions=True)
            frappe.db.commit()
            stored_count += 1
            num_comments = post_data.get('num_comments', 0)
            frappe.logger().info(
                f"Stored post {post_id} | Comments: {post_data.get('num_comments', 0)} | "
                f"Title: {post_data.get('title', '')[:50]}..."
            )
            
            
            if num_comments > 0:
                frappe.logger().info(
                    f"{'='*60}\n"
                    f"POST HAS {num_comments} COMMENTS - FETCHING NOW\n"
                    f"Post ID: {post_id}\n"
                    f"Integration: {integration_name or 'NOT SET'}\n"
                    f"{'='*60}"
                )
                
                if not integration_name:
                    frappe.logger().error(
                        f" Cannot fetch comments for {post_id}: No Reddit Integration configured!\n"
                        f"   Post has {num_comments} comments\n"
                        f"   Subreddit: r/{subreddit_name}\n"
                        f"   FIX: Configure 'Reddit Account' in Subreddit settings"
                    )
                    
                    frappe.log_error(
                        title=f"Cannot Fetch Comments - {post_id}",
                        message=f"Post {post_id} has {num_comments} comments but no Reddit Integration "
                                f"is configured for r/{subreddit_name}"
                    )
                    continue  
                try:
                    if not frappe.db.exists('Reddit Integration', integration_name):
                        frappe.logger().error(
                            f" Integration '{integration_name}' does not exist!"
                        )
                        continue
                    
                    integration_doc = frappe.get_doc('Reddit Integration', integration_name)
                    
                    if integration_doc.connection_status != 'Connected':
                        frappe.logger().error(
                            f" Integration '{integration_name}' is not connected! "
                            f"Status: {integration_doc.connection_status}"
                        )
                        continue
                    
                    frappe.logger().info(f"Integration verified and connected")
                    
                except Exception as e:
                    frappe.logger().error(f" Error verifying integration: {str(e)}")
                    continue
                
                try:
                    frappe.logger().info(
                        f"Calling fetch_and_store_comments(post_id={post_id}, limit=10, sort='top')"
                    )
                    
                    result = fetch_and_store_comments(
                        post_id=post_id,
                        limit=10,
                        sort='top'
                    )
                    
                    frappe.logger().info(f"Fetch result: {result}")
                    
                    if result.get('success'):
                        comment_count = result.get('count', 0)
                        if comment_count > 0:
                            frappe.logger().info(
                                f" SUCCESS! Fetched and stored {comment_count} comments for {post_id}"
                            )
                        else:
                            frappe.logger().warning(
                                f" Fetch returned 0 comments. Comments might be deleted/removed."
                            )
                    else:
                        error = result.get('error', 'Unknown error')
                        frappe.logger().error(f"Failed to fetch comments: {error}")
                        
                        # Queue for background processing
                        frappe.logger().info(f" Queuing background job for retry...")
                        frappe.enqueue(
                            'ai_crm.reddit_api.fetch_and_store_comments',
                            post_id=post_id,
                            limit=10,
                            sort='top',
                            queue='short',
                            timeout=60,
                        )
                        frappe.logger().info(f" Background job queued for {post_id}")
                        
                except Exception as e:
                    error_msg = f"Exception during comment fetch for {post_id}: {str(e)}"
                    frappe.logger().error(f"{error_msg}")
                    frappe.log_error(
                        title=f"Comment Fetch Exception - {post_id}",
                        message=f"{error_msg}\n{traceback.format_exc()}"
                    )
                    
                    # Still try to queue it for background
                    try:
                        frappe.enqueue(
                            'ai_crm.reddit_api.fetch_and_store_comments',
                            post_id=post_id,
                            limit=10,
                            sort='top',
                            queue='short',
                            timeout=60,
                        )
                        frappe.logger().info(f"Queued background job after exception")
                    except Exception as queue_error:
                        frappe.logger().error(f"Failed to queue job: {str(queue_error)}")
            
            else:
                frappe.logger().debug(f"Post {post_id} has 0 comments, skipping fetch")
                        
        except Exception as e:
            error_msg = f"Error storing post {post_id}: {str(e)}"
            frappe.logger().error(f"{error_msg}")
            frappe.log_error(
                title=f"Store Post Error - {post_id}",
                message=f"{error_msg}\n{traceback.format_exc()}"
            )
    
    frappe.logger().info(
        f"\n{'='*60}\n"
        f"SUMMARY: Stored {stored_count} new posts in r/{subreddit_name}\n"
        f"{'='*60}"
    )
    
    return stored_count

@frappe.whitelist()
def fetch_and_store_comments(post_id, limit=10, sort='top'):
    try:
        from datetime import datetime
        import time
        
        if not frappe.db.exists('Reddit Post', post_id):
            frappe.logger().error(f"Post {post_id} not found in database")
            return {'success': False, 'error': 'Post not found'}
        
        post_doc = frappe.get_doc('Reddit Post', post_id)
        subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
        integration_name = subreddit_doc.reddit_integration
    
        if not integration_name:
            error_msg = f"No Reddit Integration configured for subreddit: {post_doc.subreddit}"
            frappe.logger().error(error_msg)
            return {'success': False, 'error': 'No Reddit Integration configured'}
        
        frappe.logger().info(f"Fetching comments for post {post_id} using authenticated API")
        reddit_api = RedditAPI(integration_name)

        comments = reddit_api.fetch_post_comments(post_id, limit=limit, sort=sort)
        
        if not comments:
            frappe.logger().warning(f"No comments fetched for post {post_id}")
            return {'success': True, 'count': 0, 'message': 'No comments found'}
        
        # FIX: Retry logic with reload only (no direct DB insert)
        max_retries = 5
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # Reload to get latest version
                post_doc.reload()
                
                # Clear and add comments
                post_doc.set('reddit_post_comments', [])
                
                for comment in comments:
                    post_doc.append('reddit_post_comments', {
                        'author': comment.get('author', '[deleted]'),
                        'content': comment.get('body', ''),
                        'score': comment.get('score', 0)
                    })
                
                post_doc.save(ignore_permissions=True)
                frappe.db.commit()
                
                frappe.logger().info(f"✓ Stored {len(comments)} comments for post {post_id} (attempt {retry_count + 1})")
                
                return {
                    'success': True, 
                    'count': len(comments),
                    'message': f'Successfully stored {len(comments)} comments'
                }
                
            except frappe.exceptions.TimestampMismatchError as tse:
                retry_count += 1
                frappe.logger().warning(
                    f"Timestamp mismatch for {post_id} (attempt {retry_count}/{max_retries})"
                )
                
                if retry_count >= max_retries:
                    error_msg = f"Failed after {max_retries} retries due to concurrent modifications"
                    frappe.logger().error(error_msg)
                    return {
                        'success': False,
                        'error': error_msg
                    }
                
                time.sleep(0.5 * retry_count)
                continue
            
    except Exception as e:
        error_msg = f"Error fetching comments for {post_id}: {str(e)}\n{traceback.format_exc()}"
        frappe.logger().error(error_msg)
        frappe.log_error(error_msg, f"Fetch Comments Error - {post_id}")
        return {'success': False, 'error': str(e)}
    
def extract_comment_from_ai_result(result):
    """Extract clean comment text from AI result, removing ALL metadata"""
    comment_text = ""
    
    if isinstance(result, str):
        result_str = result.strip()
        
        if "comment=" in result_str.lower():
            
            patterns = [
                r"comment\s*=\s*['\"](.+?)['\"](?:\s+\w+\s*=)",  
                r"comment\s*=\s*['\"](.+?)['\"]$",             
                r"comment\s*=\s*['\"](.+)['\"]",                
            ]
            
            for pattern in patterns:
                match = re.search(pattern, result_str, re.IGNORECASE | re.DOTALL)
                if match:
                    comment_text = match.group(1).strip()
                    break
        
        elif result_str.startswith('{') and result_str.endswith('}'):
            try:
                json_result = json.loads(result_str)
                if isinstance(json_result, dict):
                    comment_text = (json_result.get('comment') or 
                                   json_result.get('response') or 
                                   json_result.get('text') or '')
            except json.JSONDecodeError:
                pass
        
        if not comment_text and not any(marker in result_str.lower() for marker in ['confidence=', 'reasoning=', 'score=']):
            comment_text = result_str
    
    elif isinstance(result, dict):
        for field_name in ['comment', 'response', 'text', 'content', 'message', 'output', 'result']:
            if field_name in result and result[field_name]:
                comment_text = str(result[field_name]).strip()
                break
    
    elif hasattr(result, '__dict__'):
        result_dict = result.__dict__
        for field_name in ['comment', 'response', 'text', 'content', 'message']:
            if field_name in result_dict and result_dict[field_name]:
                comment_text = str(result_dict[field_name]).strip()
                break
    
    if not comment_text and isinstance(result, (list, tuple)) and len(result) > 0:
        return extract_comment_from_ai_result(result[0])
    
    if comment_text:
        comment_text = re.sub(r'^comment\s*=\s*[\'"]?', '', comment_text, flags=re.IGNORECASE)
        comment_text = re.sub(r'^revise_comment\s*=\s*[\'"]?', '', comment_text, flags=re.IGNORECASE)
        comment_text = re.sub(r'[\'"]?\s+\w+\s*=.*$', '', comment_text, flags=re.IGNORECASE | re.DOTALL)
       
        for field in ['confidence', 'reasoning', 'improvements_made', 'revision_reason', 'quality_score']:
            comment_text = re.sub(rf'[\'"]?\s*{field}\s*=.*$', '', comment_text, flags=re.IGNORECASE | re.DOTALL)
        
        comment_text = comment_text.strip('\'"')
        comment_text = comment_text.strip()
        
        if any(pattern in comment_text.lower() for pattern in ['confidence=', 'reasoning=', 'score=']):
            for marker in ['confidence=', 'reasoning=', 'improvements_made=', 'revision_reason=', 'quality_score=']:
                if marker in comment_text.lower():
                    idx = comment_text.lower().index(marker)
                    comment_text = comment_text[:idx].strip().strip('\'"')
                    break
    
    return comment_text
def generate_ai_comment_internal(post_name, agent_name=None):
    try:
        post_doc = frappe.get_doc('Reddit Post', post_name)
        frappe.logger().info(f"Generating AI comment for post: {post_name}")
        
        if not agent_name:
            if not frappe.db.exists('Subreddit', post_doc.subreddit):
                return {'success': False, 'error': f'Subreddit {post_doc.subreddit} not found'}
            
            subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
            agent_name = subreddit_doc.ai_comment_agent
            
            if not agent_name:
                return {'success': False, 'error': 'No AI Comment Agent configured'}
        
        if not frappe.db.exists('AI Agent', agent_name):
            return {'success': False, 'error': f'AI Agent "{agent_name}" not found'}
    
        if not post_doc.existing_comments:
            reddit_api = RedditAPI(subreddit_doc.reddit_integration)
            existing_comments = reddit_api.fetch_post_comments(post_doc.post_id, limit=5, sort='top')
            comments_text = ""
            if existing_comments:
                comments_text = "\n\nExisting Comments:\n"
                for i, comment in enumerate(existing_comments[:5], 1):
                    comments_text += f"{i}. {comment['author']} (score: {comment['score']}): {comment['body'][:200]}\n"
                post_doc.existing_comments = comments_text
                post_doc.save(ignore_permissions=True)
        else:
            comments_text = post_doc.existing_comments

        agent_doc = frappe.get_doc('AI Agent', agent_name)
        ai_input_data = {
            "post_title": post_doc.title or "",
            "post_content": post_doc.selftext or "",
            "subreddit": post_doc.subreddit or "",
            "post_type": post_doc.post_type or "Text",
            "score": post_doc.score or 0,
            "author": post_doc.author or "",
            "existing_comments": comments_text  
        }
        
        result = agent_doc.test_agent(**ai_input_data)
        comment_text = extract_comment_from_ai_result(result)
        
        if not comment_text:
            return {'success': False, 'error': 'AI Agent returned empty comment'}
        
        post_doc.ai_generated_comment = comment_text
        post_doc.comment_status = 'Ready'
        post_doc.save()
        
        frappe.logger().info(f"✓ Generated clean comment (length: {len(comment_text)})")
        
        return {
            'success': True, 
            'comment': comment_text,
            'existing_comments_count': len(existing_comments) if 'existing_comments' in locals() else 0
        }
    except Exception as e:
        frappe.log_error(str(e), "Generate AI Comment Error")
        return {'success': False, 'error': str(e)}
    
@frappe.whitelist()
def post_comment_to_reddit(post_name):
    try:
        post_doc = frappe.get_doc('Reddit Post', post_name)
        
        if not post_doc.ai_generated_comment:
            return {
                'success': False, 
                'error': 'No AI comment to post. Generate comment first.'
            }
        
        if post_doc.comment_status == 'Commented':
            return {
                'success': False, 
                'error': 'Comment already posted'
            }
       
        clean_comment = extract_comment_from_ai_result(post_doc.ai_generated_comment)
        
        if not clean_comment or not clean_comment.strip():
            frappe.logger().error(f"Failed to extract clean comment from: {post_doc.ai_generated_comment[:200]}")
            return {
                'success': False,
                'error': 'Failed to extract clean comment text',
                'debug': post_doc.ai_generated_comment[:200]
            }
        
        frappe.logger().info(f"Clean comment extracted (length {len(clean_comment)}): {clean_comment[:100]}...")
        subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
        integration_name = getattr(subreddit_doc, 'reddit_integration', None)
        
        try:
            reddit_api = RedditAPI(integration_name)
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to initialize Reddit API: {str(e)}'
            }
        
        frappe.logger().info(f"Posting comment to post {post_doc.post_id}")
        success = reddit_api.create_comment(post_doc.post_id, clean_comment)
        
        if success:
            post_doc.comment_status = 'Commented'
            post_doc.comment_posted_at = frappe.utils.now()
            post_doc.comment_error = ''
            post_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().info(f"Successfully posted comment for {post_name}")
            
            return {
                'success': True,
                'message': 'Comment posted successfully to Reddit'
            }
        else:
            post_doc.comment_status = 'Failed'
            post_doc.comment_error = 'Failed to post comment to Reddit'
            post_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            return {
                'success': False, 
                'error': 'Failed to post comment to Reddit. Check error log for details.'
            }
        
    except Exception as e:
        error_msg = f"Error in post_comment_to_reddit: {str(e)}"
        frappe.log_error(
            title=f"Post Comment Error - {post_name}",
            message=f"{error_msg}\n{traceback.format_exc()}"
        )
        
        return {
            'success': False, 
            'error': error_msg
        }

@frappe.whitelist()
def call_ai_agent_revise(doc_name):
    try:
        post_doc = frappe.get_doc('Reddit Post', doc_name)
        
        if not post_doc.ai_generated_comment:
            return {
                'success': False,
                'error': 'No AI comment found to revise'
            }
        
        subreddit_doc = frappe.get_doc('Subreddit', post_doc.subreddit)
        revise_agent = getattr(subreddit_doc, 'comment_revise_agent', None)
        
        if not revise_agent:
            return {
                'success': False,
                'error': 'No Comment Revise Agent configured'
            }
        
        agent_doc = frappe.get_doc('AI Agent', revise_agent)
    
        original_comment = extract_comment_from_ai_result(post_doc.ai_generated_comment)
        
        ai_input_data = {
            "original_comment": original_comment,
            "post_title": post_doc.title or "",
            "post_content": post_doc.selftext or "",
            "subreddit": post_doc.subreddit or "",
            "author": post_doc.author or "",
            "score": post_doc.score or 0,
            "post_type": post_doc.post_type or "Text",
        }
        
        frappe.logger().info(f"Calling revise agent with clean comment: {original_comment[:100]}")
        result = agent_doc.test_agent(**ai_input_data)
        frappe.logger().info(f"Raw result from agent: {str(result)[:200]}")

        revised_comment = extract_comment_from_ai_result(result)
        frappe.logger().info(f"Extracted revised comment: {revised_comment[:100]}")
        
        if revised_comment and revised_comment.strip():
            
            post_doc.ai_generated_comment = revised_comment.strip()
            if hasattr(post_doc, 'revise_comment'):
                post_doc.revise_comment = ''
            
            post_doc.comment_status = 'Ready'
            post_doc.save(ignore_permissions=True)
            frappe.db.commit()
            
            frappe.logger().info(f"✓ Comment revised and saved: {revised_comment[:50]}...")
            
            return {
                'success': True,
                'message': 'Comment revised successfully',
                'revised_comment': revised_comment
            }
        else:
            frappe.logger().error(f"Empty result after extraction. Raw result was: {str(result)[:500]}")
            return {
                'success': False,
                'error': 'AI Agent returned empty response after extraction',
                'debug': str(result)[:200]
            }
            
    except Exception as e:
        error_msg = f"Error in call_ai_agent_revise: {str(e)}\n{traceback.format_exc()}"
        frappe.logger().error(error_msg)
        frappe.log_error(error_msg, "call_ai_agent_revise Error")
        return {'success': False, 'error': str(e)}
        
@frappe.whitelist()
def generate_ai_comment(post_name, agent_name=None):
    try:
        frappe.logger().info(
            f"generate_ai_comment called with post_name: {post_name}, agent_name: {agent_name}"
        )
        return generate_ai_comment_internal(post_name, agent_name)
    except Exception as e:
        frappe.logger().error(f"Error in generate_ai_comment for {post_name}: {str(e)}")
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def fetch_posts_manually(subreddit_name, sort_type="hot", limit=5, time_filter="week", integration_name=None):
    try:
        
        if not integration_name and frappe.db.exists('Subreddit', subreddit_name):
            subreddit_doc = frappe.get_doc('Subreddit', subreddit_name)
            integration_name = subreddit_doc.reddit_integration  
        reddit_api = RedditAPI(integration_name)
        posts = reddit_api.fetch_reddit_posts(subreddit_name, sort_type, limit, time_filter)
        
        frappe.logger().info(f"Fetched {len(posts)} posts, storing in DB...")  
        
        stored_count = store_posts_in_db(subreddit_name, posts)
        
        frappe.logger().info(f"Stored {stored_count} posts successfully")  
        
        if frappe.db.exists('Subreddit', subreddit_name):
            subreddit_doc = frappe.get_doc('Subreddit', subreddit_name)
            subreddit_doc.last_monitored = frappe.utils.now()
            subreddit_doc.posts_fetched_today = (getattr(subreddit_doc, 'posts_fetched_today', 0) or 0) + stored_count
            subreddit_doc.total_posts_monitored = (getattr(subreddit_doc, 'total_posts_monitored', 0) or 0) + stored_count
            subreddit_doc.last_error = ''
            subreddit_doc.save()
            frappe.db.commit()  
        
        return {
            'success': True,
            'count': stored_count,
            'fetched': len(posts),  
            'sort_type': sort_type,
            'time_filter': time_filter if sort_type in ['top', 'controversial'] else 'N/A'
        }
    except Exception as e:
        error_msg = f"Error in fetch_posts_manually: {str(e)}\n{traceback.format_exc()}"
        frappe.log_error(error_msg)
        return {'success': False, 'error': str(e)}

@frappe.whitelist()
def get_post_statistics(subreddit_name):
    
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
        frappe.log_error(f"Error in get_post_statistics: {str(e)}\n{traceback.format_exc()}")
        frappe.throw(str(e))

@frappe.whitelist()
def get_recent_error_logs(limit=10):
    """Get recent error logs related to Reddit operations"""
    try:
        logs = frappe.get_all(
            'Error Log',
            filters={
                'error': ['like', '%reddit%']
            },
            fields=['name', 'error', 'creation'],
            order_by='creation desc',
            limit=limit
        )
        return {'success': True, 'logs': logs}
    except Exception as e:
        return {'success': False, 'error': str(e)}
