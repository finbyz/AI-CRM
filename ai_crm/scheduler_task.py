# ai_crm/scheduler_tasks.py
import frappe
from frappe.utils import now, add_to_date, get_datetime
from ai_crm.reddit_api import RedditAPI, store_posts_in_db

def fetch_and_store_posts():
    """Scheduler task to fetch posts from all active subreddits"""
    try:
        frappe.logger().info("Starting scheduled task: fetch_and_store_posts")
        
        # Get all active subreddits that need monitoring
        subreddits = frappe.get_all(
            'Subreddit',
            filters={
                'is_active': 1,
                'docstatus': ['!=', 2]
            },
            fields=['name', 'subreddit_name', 'monitor_frequency', 'last_monitored']
        )
        
        if not subreddits:
            frappe.logger().info("No active subreddits found for monitoring")
            return
        
        reddit_api = RedditAPI()
        current_time = get_datetime()
        processed_count = 0
        
        for subreddit in subreddits:
            try:
                # Check if it's time to monitor this subreddit
                if subreddit.last_monitored:
                    next_monitor_time = add_to_date(
                        subreddit.last_monitored, 
                        minutes=subreddit.monitor_frequency
                    )
                    
                    if current_time < next_monitor_time:
                        frappe.logger().debug(
                            f"Skipping r/{subreddit.subreddit_name} - not time yet"
                        )
                        continue
                
                frappe.logger().info(f"Fetching posts from r/{subreddit.subreddit_name}")
                
                # Fetch posts
                posts = reddit_api.fetch_reddit_posts(subreddit.subreddit_name)
                
                if not posts:
                    frappe.logger().info(f"No new posts found in r/{subreddit.subreddit_name}")
                    continue
                
                # Store posts in database
                stored_count = store_posts_in_db(subreddit.subreddit_name, posts)
                
                # Update subreddit statistics
                subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                subreddit_doc.last_monitored = current_time
                subreddit_doc.posts_fetched_today = (subreddit_doc.posts_fetched_today or 0) + stored_count
                subreddit_doc.total_posts_monitored = (subreddit_doc.total_posts_monitored or 0) + stored_count
                subreddit_doc.last_error = ''
                subreddit_doc.save()
                
                processed_count += 1
                frappe.logger().info(f"Stored {stored_count} new posts from r/{subreddit.subreddit_name}")
                
            except Exception as e:
                # Log error to subreddit
                try:
                    subreddit_doc = frappe.get_doc('Subreddit', subreddit.name)
                    subreddit_doc.last_error = str(e)[:500]  # Limit error message length
                    subreddit_doc.save()
                except Exception as save_error:
                    frappe.logger().error(f"Failed to save error to subreddit: {str(save_error)}")
                
                frappe.log_error(
                    message=str(e), 
                    title=f"Error processing subreddit {subreddit.subreddit_name}"
                )
        
        # Commit all changes
        
        frappe.logger().info(f"Completed fetch_and_store_posts - processed {processed_count} subreddits")
        
    except Exception as e:
        frappe.log_error(
            message=str(e), 
            title="Error in fetch_and_store_posts scheduler task"
        )
        frappe.logger().error(f"Critical error in fetch_and_store_posts: {str(e)}")

def auto_comment_on_posts():
    """Scheduler task to automatically comment on eligible posts"""
    try:
        frappe.logger().info("Starting scheduled task: auto_comment_on_posts")
        
        # Get subreddits with auto_comment enabled
        subreddits = frappe.get_all(
            'Subreddit',
            filters={'auto_comment_enabled': 1, 'is_active': 1},
            fields=['name', 'subreddit_name', 'comment_template', 'comment_delay_minutes']
        )
        
        if not subreddits:
            frappe.logger().info("No subreddits with auto-comment enabled")
            return
        
        reddit_api = RedditAPI()
        current_time = get_datetime()
        total_commented = 0
        
        for subreddit in subreddits:
            if not subreddit.comment_template:
                frappe.logger().warning(f"No comment template for {subreddit.subreddit_name}")
                continue
            
            try:
                # Calculate delay time
                delay_minutes = subreddit.comment_delay_minutes or 30  # Default 30 minutes
                delay_time = add_to_date(current_time, minutes=-delay_minutes)
                
                # Get posts ready for commenting
                posts = frappe.get_all(
                    'Reddit Post',
                    filters={
                        'subreddit': subreddit.name,
                        'comment_status': 'Ready',
                        'created_utc': ['<=', delay_time]
                    },
                    fields=['name', 'post_id', 'title'],
                    limit=10  # Process 10 posts at a time to avoid rate limits
                )
                
                if not posts:
                    frappe.logger().debug(f"No posts ready for commenting in {subreddit.subreddit_name}")
                    continue
                
                frappe.logger().info(f"Processing {len(posts)} posts for commenting in {subreddit.subreddit_name}")
                
                for post in posts:
                    try:
                        # Post comment
                        success = reddit_api.post_comment(post.post_id, subreddit.comment_template)
                        
                        # Update post status
                        post_doc = frappe.get_doc('Reddit Post', post.name)
                        if success:
                            post_doc.comment_status = 'Commented'
                            post_doc.comment_posted_at = current_time
                            post_doc.comment_error = ''
                            total_commented += 1
                            frappe.logger().info(f"Successfully commented on post {post.post_id}")
                        else:
                            post_doc.comment_status = 'Failed'
                            post_doc.comment_error = 'Failed to post comment'
                            frappe.logger().warning(f"Failed to comment on post {post.post_id}")
                        
                        post_doc.save()
                        
                        # Add small delay between comments to avoid rate limiting
                        import time
                        time.sleep(1)
                        
                    except Exception as e:
                        # Update post with error
                        try:
                            post_doc = frappe.get_doc('Reddit Post', post.name)
                            post_doc.comment_status = 'Failed'
                            post_doc.comment_error = str(e)[:500]  # Limit error message length
                            post_doc.save()
                        except Exception as save_error:
                            frappe.logger().error(f"Failed to save comment error: {str(save_error)}")
                        
                        frappe.log_error(
                            message=str(e),
                            title=f"Error commenting on post {post.post_id}"
                        )
            
            except Exception as e:
                frappe.log_error(
                    message=str(e),
                    title=f"Error processing comments for subreddit {subreddit.subreddit_name}"
                )
        
        # Commit all changes
        
        frappe.logger().info(f"Completed auto_comment_on_posts - commented on {total_commented} posts")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in auto_comment_on_posts scheduler task"
        )
        frappe.logger().error(f"Critical error in auto_comment_on_posts: {str(e)}")

def reset_daily_counters():
    """Reset daily post counters at midnight"""
    try:
        frappe.logger().info("Starting scheduled task: reset_daily_counters")
        
        result = frappe.db.sql("UPDATE `tabSubreddit` SET posts_fetched_today = 0")
        
        
        frappe.logger().info("Successfully reset daily counters")
        
    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Error in reset_daily_counters scheduler task"
        )
        frappe.logger().error(f"Critical error in reset_daily_counters: {str(e)}")

# Test functions to manually trigger scheduler tasks
@frappe.whitelist()
def test_fetch_and_store():
    """Test function to manually trigger fetch_and_store_posts"""
    try:
        fetch_and_store_posts()
        return {"status": "success", "message": "fetch_and_store_posts completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist() 
def test_auto_comment():
    """Test function to manually trigger auto_comment_on_posts"""
    try:
        auto_comment_on_posts()
        return {"status": "success", "message": "auto_comment_on_posts completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@frappe.whitelist()
def test_reset_counters():
    """Test function to manually trigger reset_daily_counters"""
    try:
        reset_daily_counters()
        return {"status": "success", "message": "reset_daily_counters completed"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

# Utility function to check scheduler status
@frappe.whitelist()
def get_scheduler_status():
    """Check if scheduler is enabled and running"""
    try:
        scheduler_status = {
            "scheduler_enabled": frappe.utils.cint(frappe.db.get_single_value("System Settings", "enable_scheduler")),
            "current_time": frappe.utils.now(),
            "last_fetch_job": None,
            "last_comment_job": None,
            "active_subreddits": frappe.db.count("Subreddit", {"is_active": 1}),
            "pending_comments": frappe.db.count("Reddit Post", {"comment_status": "Pending"})
        }
        
        # Check for recent scheduler logs
        recent_logs = frappe.get_all(
            "Error Log",
            filters={
                "error": ["like", "%scheduler%"],
                "creation": [">=", frappe.utils.add_days(frappe.utils.now(), -1)]
            },
            fields=["name", "error", "creation"],
            limit=5,
            order_by="creation desc"
        )
        
        scheduler_status["recent_scheduler_logs"] = recent_logs
        
        return scheduler_status
    except Exception as e:
        return {"status": "error", "message": str(e)}